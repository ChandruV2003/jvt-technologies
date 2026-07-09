#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
VOICE_ROOT = REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "jvt-inbound-voice-agent"
QUALITY_ROOT = VOICE_ROOT / "voice-quality"
ENV_PATH = VOICE_ROOT / ".env.local"
REPORT_JSON = STATE_ROOT / "latest-voice-readiness.json"
REPORT_MD = STATE_ROOT / "latest-voice-readiness.md"
MODEL_ROUTER_HEALTH_URL = "http://127.0.0.1:8760/health"
DEFAULT_LOCAL_AUDIO_BRIDGE_HEALTH_URL = "http://127.0.0.1:8761/health"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def count_files(path: Path, suffixes: tuple[str, ...]) -> int:
    if not path.exists():
        return 0
    suffix_set = {suffix.lower() for suffix in suffixes}
    return sum(1 for item in path.glob("*") if item.is_file() and item.suffix.lower() in suffix_set)


def latest_file(path: Path, suffixes: tuple[str, ...]) -> str:
    if not path.exists():
        return ""
    suffix_set = {suffix.lower() for suffix in suffixes}
    files = [item for item in path.glob("*") if item.is_file() and item.suffix.lower() in suffix_set]
    if not files:
        return ""
    return str(max(files, key=lambda item: item.stat().st_mtime))


def http_health(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "jvt-voice-readiness/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read().decode("utf-8", errors="ignore")[:500]
            compact = body.replace(" ", "").replace("\n", "")
            ok = response.status == 200 and ('"status":"ok"' in compact or '"ok":true' in compact)
            return {"ok": ok, "status": response.status, "body_preview": body}
    except (OSError, urllib.error.URLError) as exc:
        return {"ok": False, "error": str(exc)}


def build_report() -> dict[str, Any]:
    env = load_env(ENV_PATH)
    public_base_url = env.get("JVT_VOICE_PUBLIC_BASE_URL", "")
    response_engine = (env.get("JVT_VOICE_RESPONSE_ENGINE") or os.environ.get("JVT_VOICE_RESPONSE_ENGINE") or "local-model-router").lower()
    has_openai_key = bool(env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    dry_run = str(env.get("JVT_VOICE_DRY_RUN", "1")).lower() in {"1", "true", "yes", "on"}
    phone_provider_configured = str(env.get("JVT_VOICE_PHONE_PROVIDER_CONFIGURED", "0")).lower() in {"1", "true", "yes", "on"}
    local_audio_bridge_ready = str(env.get("JVT_VOICE_LOCAL_AUDIO_BRIDGE_READY", "0")).lower() in {"1", "true", "yes", "on"}
    local_audio_bridge_health_url = env.get("JVT_VOICE_LOCAL_AUDIO_BRIDGE_HEALTH_URL") or DEFAULT_LOCAL_AUDIO_BRIDGE_HEALTH_URL
    openai_required = response_engine in {"openai", "openai-realtime"}
    public_health_url = f"{public_base_url.rstrip('/')}/health" if public_base_url.startswith("http") else ""
    samples = QUALITY_ROOT / "samples"
    normalized = QUALITY_ROOT / "normalized"
    renders = QUALITY_ROOT / "renders"
    scorecards = QUALITY_ROOT / "scorecards"
    sample_count = count_files(samples, (".webm", ".wav", ".m4a", ".mp3"))
    metadata_count = count_files(samples, (".json",))
    normalized_count = count_files(normalized, (".wav",))
    render_count = count_files(renders, (".wav", ".mp3", ".json"))
    scorecard_count = count_files(scorecards, (".json", ".md"))
    local_health = http_health("http://127.0.0.1:8066/health")
    model_router_health = http_health(MODEL_ROUTER_HEALTH_URL)
    local_audio_bridge_health = http_health(local_audio_bridge_health_url) if response_engine in {"local-audio-bridge", "local-realtime"} else {"ok": False, "skipped": True}
    public_health = http_health(public_health_url) if public_health_url else {"ok": False, "error": "No public base URL configured."}
    local_model_router_ok = bool(model_router_health.get("ok"))
    live_audio_backend_ready = (openai_required and has_openai_key) or (
        response_engine in {"local-audio-bridge", "local-realtime"} and local_audio_bridge_ready and bool(local_audio_bridge_health.get("ok"))
    )
    gates = {
        "app_exists": VOICE_ROOT.exists(),
        "local_health_ok": bool(local_health.get("ok")),
        "public_health_ok": bool(public_health.get("ok")),
        "local_model_router_ok": local_model_router_ok,
        "sample_count_ready": sample_count >= 10,
        "normalized_ready": normalized_count >= 10,
        "render_exists": render_count > 0,
        "scorecard_exists": scorecard_count > 0,
        "openai_key_present": has_openai_key,
        "openai_required": openai_required,
        "local_audio_bridge_ready": local_audio_bridge_ready,
        "live_audio_backend_ready": live_audio_backend_ready,
        "public_https_url": public_base_url.startswith("https://"),
        "dry_run_disabled": not dry_run,
        "phone_provider_configured": phone_provider_configured,
    }
    demo_ready = all(gates[key] for key in ("app_exists", "local_health_ok", "local_model_router_ok", "sample_count_ready", "normalized_ready", "render_exists", "scorecard_exists"))
    live_gate_names = ("public_health_ok", "public_https_url", "dry_run_disabled", "phone_provider_configured", "live_audio_backend_ready")
    live_ready = demo_ready and all(gates[key] for key in live_gate_names)
    blockers = [
        key
        for key, value in gates.items()
        if not value and key not in {"openai_key_present", "openai_required", "local_audio_bridge_ready"}
    ]
    return {
        "generated_at": utc_now(),
        "ok": demo_ready,
        "demo_ready": demo_ready,
        "live_ready": live_ready,
        "mode": "live-ready" if live_ready else "demo-ready" if demo_ready else "setup",
        "voice_root": str(VOICE_ROOT),
        "public_base_url": public_base_url,
        "response_engine": response_engine,
        "openai_required": openai_required,
        "local_health": local_health,
        "model_router_health": model_router_health,
        "local_audio_bridge_health": local_audio_bridge_health,
        "local_audio_bridge_health_url": local_audio_bridge_health_url,
        "public_health": public_health,
        "sample_count": sample_count,
        "sample_metadata_count": metadata_count,
        "normalized_count": normalized_count,
        "render_count": render_count,
        "scorecard_count": scorecard_count,
        "latest_render": latest_file(renders, (".wav", ".mp3")),
        "latest_scorecard": latest_file(scorecards, (".json", ".md")),
        "gates": gates,
        "blockers": blockers,
        "next_action": (
            "Ready for controlled internal demo and scoring; live phone deployment still requires explicit operator approval."
            if demo_ready and not live_ready
            else "Resolve missing readiness gates before using this voice path in a customer demo."
            if not demo_ready
            else "Live gates are technically satisfied; still require explicit approval before any live call traffic."
        ),
        "safety_boundary": "Use consented internal voice samples only. Do not deploy outbound calls or undisclosed voice use from this report.",
        "model_boundary": "Reasoning/intake should use the local model router or capped Codex CLI. OpenAI Realtime is optional and not required for JVT readiness.",
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Voice Readiness",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Demo ready: `{report['demo_ready']}`",
        f"- Live ready: `{report['live_ready']}`",
        f"- Response engine: `{report.get('response_engine')}`",
        f"- Samples: `{report['sample_count']}` raw / `{report['normalized_count']}` normalized",
        f"- Renders: `{report['render_count']}`",
        f"- Scorecards: `{report['scorecard_count']}`",
        f"- Safety: {report['safety_boundary']}",
        f"- Model boundary: {report['model_boundary']}",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in report["blockers"])
    else:
        lines.append("- None.")
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or "")])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    write_json(REPORT_JSON, report)
    write_markdown(report)
    print(json.dumps({"ok": report["ok"], "mode": report["mode"], "demo_ready": report["demo_ready"], "live_ready": report["live_ready"]}))


if __name__ == "__main__":
    main()
