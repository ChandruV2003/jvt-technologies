#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
CONTROL_ROOT = ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
TASK_ROOT = CONTROL_ROOT / "tasks"
WATCHDOG_STATE = ROOT / "ops" / "watchdog" / "state" / "latest-watchdog.json"
MODEL_ROUTER_STATE = STATE_ROOT / "latest-model-router.json"
CODEX_ESCALATION_STATE = STATE_ROOT / "latest-codex-escalation.json"
OPS_DB_STATE = STATE_ROOT / "latest-jvt-ops-db.json"
OPPORTUNITY_STATE = STATE_ROOT / "latest-opportunity-manager.json"
VOICE_READINESS_STATE = STATE_ROOT / "latest-voice-readiness.json"
PAPER_TRADER_HEALTH_STATE = STATE_ROOT / "latest-paper-trader-health.json"
SOURCE_HYGIENE_STATE = STATE_ROOT / "latest-source-hygiene.json"
SYSTEM_RESOURCES_STATE = STATE_ROOT / "latest-system-resources.json"
LEAD_RESEARCH_STATUS = ROOT / "lead-pipeline" / "state" / "auto-research-status.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def safe_count(path: Path) -> int:
    return sum(1 for item in path.glob("*.json") if item.is_file()) if path.exists() else 0


def task_exists(task_id: str) -> bool:
    for folder in ("pending", "running", "completed", "failed", "held"):
        if (TASK_ROOT / folder / f"{task_id}.json").exists():
            return True
    return False


def make_task(task_id: str, task_type: str, goal: str) -> dict[str, Any] | None:
    if task_exists(task_id):
        return None
    return {
        "id": task_id,
        "type": task_type,
        "priority": "ai-director",
        "created_at": utc_now(),
        "goal": goal,
        "requires_approval": False,
        "seeded_by": "ai_director",
    }


def mlx_generate(prompt: str) -> dict[str, Any]:
    host = (os.environ.get("JVT_MLX_HOST") or "http://127.0.0.1:11435").rstrip("/")
    model = os.environ.get("JVT_MLX_MODEL") or "mlx-community/Qwen3-8B-4bit"
    timeout_seconds = float(os.environ.get("JVT_AI_DIRECTOR_TIMEOUT_SECONDS") or "35")
    num_predict = int(os.environ.get("JVT_AI_DIRECTOR_NUM_PREDICT") or "220")
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": num_predict,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"available": False, "backend": "m4-mlx", "reason": str(exc)}
    choices = data.get("choices") or []
    message = ((choices[0] or {}).get("message") or {}) if choices else {}
    return {
        "available": True,
        "backend": "m4-mlx",
        "model": model,
        "response": str(message.get("content") or "").strip()[:4000],
    }


def router_generate(prompt: str) -> dict[str, Any]:
    host = (os.environ.get("JVT_MODEL_ROUTER_HOST") or "http://127.0.0.1:8760").rstrip("/")
    timeout_seconds = float(os.environ.get("JVT_AI_DIRECTOR_TIMEOUT_SECONDS") or "35")
    num_predict = int(os.environ.get("JVT_AI_DIRECTOR_NUM_PREDICT") or "220")
    payload = json.dumps({
        "task_type": "status_summary",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": num_predict,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"available": False, "backend": "model-router", "reason": str(exc)}
    choices = data.get("choices") or []
    message = ((choices[0] or {}).get("message") or {}) if choices else {}
    return {
        "available": True,
        "backend": "model-router",
        "router": data.get("jvt_router"),
        "response": str(message.get("content") or "").strip()[:4000],
    }


def ollama_generate(prompt: str) -> dict[str, Any]:
    host = os.environ.get("JVT_OLLAMA_HOST") or os.environ.get("OLLAMA_HOST") or ""
    model = os.environ.get("JVT_AI_DIRECTOR_MODEL") or os.environ.get("OLLAMA_MODEL") or ""
    timeout_seconds = float(os.environ.get("JVT_AI_DIRECTOR_TIMEOUT_SECONDS") or "35")
    num_predict = int(os.environ.get("JVT_AI_DIRECTOR_NUM_PREDICT") or "320")
    if not host or not model:
        return {
            "available": False,
            "reason": "JVT_OLLAMA_HOST/OLLAMA_HOST and JVT_AI_DIRECTOR_MODEL/OLLAMA_MODEL are not configured for this worker.",
        }
    host = host.rstrip("/")
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": num_predict,
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": str(exc)}
    return {
        "available": True,
        "backend": "ollama",
        "model": model,
        "response": str(data.get("response") or "").strip()[:4000],
    }


def local_model_generate(prompt: str) -> dict[str, Any]:
    backend = os.environ.get("JVT_AI_DIRECTOR_BACKEND", "router").strip().lower()
    if backend == "ollama":
        return ollama_generate(prompt)
    if backend == "router":
        result = router_generate(prompt)
        if result.get("available"):
            return result
    result = mlx_generate(prompt)
    if result.get("available"):
        return result
    fallback = ollama_generate(prompt)
    if fallback.get("available"):
        fallback["fallback_from"] = result
        return fallback
    return result


def build_snapshot() -> dict[str, Any]:
    orchestrator = load_json(STATE_ROOT / "latest-orchestrator.json", {})
    watchdog = load_json(WATCHDOG_STATE, {})
    eom = load_json(STATE_ROOT / "latest-eom-brief.json", {})
    auto_send = load_json(ROOT / "outreach" / "schedules" / "auto-send" / "latest-auto-send.json", {})
    followup_review = load_json(ROOT / "outreach" / "schedules" / "followups" / "latest-auto-approve-followups.json", {})
    initial_review = load_json(ROOT / "outreach" / "schedules" / "initial-auto-review" / "latest-auto-approve-initials.json", {})
    model_router = load_json(MODEL_ROUTER_STATE, {})
    codex_escalation = load_json(CODEX_ESCALATION_STATE, {})
    ops_db = load_json(OPS_DB_STATE, {})
    opportunity_manager = load_json(OPPORTUNITY_STATE, {})
    voice_readiness = load_json(VOICE_READINESS_STATE, {})
    paper_trader_health = load_json(PAPER_TRADER_HEALTH_STATE, {})
    source_hygiene = load_json(SOURCE_HYGIENE_STATE, {})
    system_resources = load_json(SYSTEM_RESOURCES_STATE, {})
    lead_research = load_json(LEAD_RESEARCH_STATUS, {})
    queues = {name: safe_count(ROOT / "outreach" / "queue" / name) for name in ("draft", "review", "approved", "sent", "replied")}
    return {
        "orchestrator": {
            "generated_at": orchestrator.get("generated_at"),
            "status": orchestrator.get("status"),
            "quotas": orchestrator.get("quotas"),
            "work_item_count": len(orchestrator.get("work_items") or []) if isinstance(orchestrator.get("work_items"), list) else 0,
        },
        "watchdog": {
            "generated_at": watchdog.get("generated_at"),
            "overall_ok": watchdog.get("overall_ok"),
            "finding_count": len(watchdog.get("findings") or []),
            "critical_findings": [item for item in (watchdog.get("findings") or []) if item.get("severity") == "critical"],
        },
        "eom": {
            "generated_at": eom.get("generated_at"),
            "status": eom.get("status"),
            "focus": eom.get("focus"),
        },
        "auto_send": {
            "generated_at": auto_send.get("generated_at"),
            "status": auto_send.get("status"),
            "block_reason": auto_send.get("block_reason"),
            "sent_after": auto_send.get("sent_after"),
            "held_by_runner": auto_send.get("held_by_runner"),
        },
        "auto_review": {
            "followups": {
                "generated_at": followup_review.get("generated_at"),
                "approved_count": followup_review.get("approved_count"),
                "held_count": followup_review.get("held_count"),
            },
            "initials": {
                "generated_at": initial_review.get("generated_at"),
                "approved_count": initial_review.get("approved_count"),
                "held_count": initial_review.get("held_count"),
            },
        },
        "queues": queues,
        "model_router": {
            "generated_at": model_router.get("generated_at"),
            "ok": model_router.get("ok"),
            "available_backends": model_router.get("available_backends"),
            "backends": {
                name: {
                    "available": item.get("available"),
                    "state": item.get("state"),
                    "model": item.get("model"),
                }
                for name, item in ((model_router.get("backends") or {}).items())
            },
        },
        "codex_escalation": {
            "generated_at": codex_escalation.get("generated_at"),
            "ok": codex_escalation.get("ok"),
            "enabled": codex_escalation.get("enabled"),
            "usage": codex_escalation.get("usage"),
        },
        "ops_db": {
            "generated_at": ops_db.get("generated_at"),
            "ok": ops_db.get("ok"),
            "db_path": ops_db.get("db_path"),
            "table_counts": ops_db.get("table_counts"),
            "queue_counts": ops_db.get("queue_counts"),
            "inbox_counts": ops_db.get("inbox_counts"),
        },
        "opportunity_manager": {
            "generated_at": opportunity_manager.get("generated_at"),
            "active_count": opportunity_manager.get("active_count"),
            "response_needed_count": opportunity_manager.get("response_needed_count"),
            "top_next_actions": opportunity_manager.get("top_next_actions"),
        },
        "voice_readiness": {
            "generated_at": voice_readiness.get("generated_at"),
            "demo_ready": voice_readiness.get("demo_ready"),
            "live_ready": voice_readiness.get("live_ready"),
            "mode": voice_readiness.get("mode"),
            "blockers": voice_readiness.get("blockers"),
            "gates": voice_readiness.get("gates"),
            "local_audio_bridge_health": voice_readiness.get("local_audio_bridge_health"),
            "response_engine": voice_readiness.get("response_engine"),
        },
        "paper_trader_health": {
            "generated_at": paper_trader_health.get("generated_at"),
            "ok": paper_trader_health.get("ok"),
            "mode": paper_trader_health.get("mode"),
            "findings": paper_trader_health.get("findings"),
            "decision": paper_trader_health.get("decision"),
        },
        "lead_research": {
            "generated_at": lead_research.get("generated_at"),
            "new_leads_added": lead_research.get("new_leads_added"),
            "drafts_created": lead_research.get("drafts_created"),
            "drop_reasons": lead_research.get("drop_reasons"),
            "queries": lead_research.get("queries"),
        },
        "source_hygiene": {
            "generated_at": source_hygiene.get("generated_at"),
            "status_count": source_hygiene.get("status_count"),
            "important_changes": source_hygiene.get("important_changes"),
        },
        "system_resources": {
            "generated_at": system_resources.get("generated_at"),
            "ok": system_resources.get("ok"),
            "findings": system_resources.get("findings"),
            "tcp": system_resources.get("tcp"),
        },
    }


def deterministic_directives(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    quotas = ((snapshot.get("orchestrator") or {}).get("quotas") or {})
    queues = snapshot.get("queues") or {}
    directives: list[dict[str, Any]] = []

    if (snapshot.get("watchdog") or {}).get("critical_findings"):
        directives.append({
            "priority": 1,
            "lane": "ops-health",
            "action": "Fix critical watchdog findings before send expansion.",
            "autonomous": True,
        })
        return directives

    if not (snapshot.get("model_router") or {}).get("ok"):
        directives.append({
            "priority": 1,
            "lane": "model-runtime",
            "action": "Repair or start the model router before assigning heavy model-backed tasks.",
            "autonomous": True,
        })

    if not (snapshot.get("ops_db") or {}).get("ok"):
        directives.append({
            "priority": 1,
            "lane": "company-memory",
            "action": "Sync the JVT ops database so leads, queues, services, and model backend state have a durable source of truth.",
            "autonomous": True,
        })

    if not (snapshot.get("codex_escalation") or {}).get("ok"):
        directives.append({
            "priority": 2,
            "lane": "codex-escalation",
            "action": "Keep Codex escalation disabled for autonomous use until CLI auth, policy, and daily caps report ready.",
            "autonomous": True,
        })

    voice = snapshot.get("voice_readiness") or {}
    voice_gates = voice.get("gates") if isinstance(voice.get("gates"), dict) else {}
    bridge_health = voice.get("local_audio_bridge_health") if isinstance(voice.get("local_audio_bridge_health"), dict) else {}
    if voice.get("demo_ready") and not voice.get("live_ready") and not voice_gates.get("local_audio_bridge_ready"):
        directives.append({
            "priority": 2,
            "lane": "voice-bridge",
            "action": (
                "Local audio bridge is present but not live-ready. Create and execute the next internal bridge-readiness "
                f"task before treating voice as production-capable. Bridge health: {bridge_health.get('service_status') or bridge_health.get('status') or 'unknown'}."
            ),
            "autonomous": True,
        })

    if int(queues.get("review") or 0) > 25:
        directives.append({
            "priority": 1,
            "lane": "outreach-quality",
            "action": "Continue strict auto-review of review backlog; promote only clean packets and hold questionable records.",
            "autonomous": True,
        })
    lead_research = snapshot.get("lead_research") or {}
    new_leads_added = int(lead_research.get("new_leads_added") or 0)
    drop_reasons = lead_research.get("drop_reasons") if isinstance(lead_research.get("drop_reasons"), dict) else {}
    if new_leads_added <= 1:
        top_drop = ", ".join(f"{key}={value}" for key, value in sorted(drop_reasons.items(), key=lambda item: (-int(item[1]), item[0]))[:3])
        directives.append({
            "priority": 2,
            "lane": "lead-source-quality",
            "action": f"Lead research is starved or weak. Rotate higher-intent vertical queries and inspect drop reasons before loosening gates. Top drops: {top_drop or 'none recorded'}.",
            "autonomous": True,
        })
    if int(quotas.get("approved_backlog") or 0) > 0 and bool(quotas.get("send_allowed_now")):
        directives.append({
            "priority": 2,
            "lane": "outreach-send",
            "action": "Run quality-gated auto-send within current caps; do not exceed daily sender limits.",
            "autonomous": True,
        })
    if int(quotas.get("eligible_followups") or 0) > 0:
        directives.append({
            "priority": 3,
            "lane": "followups",
            "action": "Generate and strictly review no-reply follow-ups; no-reply remains an active queue state.",
            "autonomous": True,
        })
    if int(((snapshot.get("orchestrator") or {}).get("work_item_count") or 0)) > 0:
        directives.append({
            "priority": 3,
            "lane": "work-materializer",
            "action": "Materialize current orchestrator work items into allowlisted internal tasks or capped epic specs so detected gaps become executable work.",
            "autonomous": True,
        })
    directives.append({
        "priority": 4,
        "lane": "revenue-development",
        "action": "Refresh the $10k execution digest, proof assets, and offer segment summary through allowlisted local tasks.",
        "autonomous": True,
    })
    directives.append({
        "priority": 4,
        "lane": "opportunity-memory",
        "action": "Refresh inbound hit tracking and service-pilot opportunity state through allowlisted local tasks.",
        "autonomous": True,
    })
    directives.append({
        "priority": 5,
        "lane": "vertical-lead-research",
        "action": "Refresh research for active service lanes and stage only quality-gated packet candidates.",
        "autonomous": True,
    })
    directives.append({
        "priority": 5,
        "lane": "business-readiness",
        "action": "Run the consolidated business-readiness sweep so opportunities, voice, paper trading, source hygiene, and M4 resources stay visible.",
        "autonomous": True,
    })
    return directives


def seed_director_tasks(directives: list[dict[str, Any]], *, write: bool) -> list[dict[str, Any]]:
    today = datetime.now().date().isoformat()
    hour_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d-h%H")
    candidates = [
        make_task(f"{today}-ai-director-model-router-status", "model_router_status", "AI Director requested model router readiness refresh."),
        make_task(f"{today}-ai-director-codex-escalation-status", "codex_escalation_status", "AI Director requested Codex escalation readiness refresh without executing Codex."),
        make_task(f"{today}-ai-director-jvt-ops-db-sync", "jvt_ops_db_sync", "AI Director requested JVT ops database sync."),
        make_task(f"{today}-ai-director-refresh-growth-state", "refresh_growth_state", "AI Director requested fresh growth/orchestrator/EOM/interop state."),
        make_task(f"{today}-ai-director-priority-packet-review-queue", "priority_packet_review_queue", "AI Director requested refreshed priority packet review queue."),
        make_task(f"{today}-ai-director-10k-execution-digest", "ten_k_execution_digest", "AI Director requested refreshed $10k execution digest."),
        make_task(f"{today}-ai-director-opportunity-hit-sync", "opportunity_hit_sync", "AI Director requested refreshed inbound hit and opportunity memory state."),
        make_task(f"{today}-ai-director-business-readiness-sweep", "business_readiness_sweep", "AI Director requested consolidated readiness state for opportunities, voice, trader, source, and M4 resources."),
        make_task(f"{today}-ai-director-vertical-lead-research-refresh", "vertical_lead_research_refresh", "AI Director requested refreshed vertical lead research for active service lines."),
        make_task(f"{today}-ai-director-service-pilot-package-refresh", "service_pilot_package_refresh", "AI Director requested refreshed pilot proof packages for active service lines."),
    ]
    if any(item.get("lane") == "work-materializer" for item in directives):
        task = make_task(
            f"{hour_bucket}-ai-director-work-item-materializer",
            "work_item_materializer",
            "AI Director requested materializing current orchestrator work items into allowlisted internal tasks or capped epic specs.",
        )
        if task:
            task.update({
                "lane": "work-materializer",
                "approval_boundary": "Create internal tasks/specs only. No external outreach delivery, spending, market orders, crypto custody/network participation, public release, or external commitments.",
            })
            candidates.append(task)
    if any(item.get("lane") == "lead-source-quality" for item in directives):
        task = make_task(
            f"{hour_bucket}-ai-director-lead-source-quality-refresh",
            "vertical_lead_research_refresh",
            "AI Director requested another targeted lead research pass because the previous pass was starved or weak.",
        )
        if task:
            task.update({
                "lanes": ["dental_voice", "it_ballot", "local_receptionist", "insurance", "property", "construction"],
                "queries_per_run": 8,
                "results_per_query": 10,
                "max_new_leads": 8,
                "draft_limit": 4,
            })
            candidates.append(task)
    if any(item.get("lane") == "voice-bridge" for item in directives):
        task = make_task(
            f"{hour_bucket}-ai-director-local-audio-bridge-next-step",
            "local_audio_bridge_next_step",
            "AI Director detected the local audio bridge is running but not ready and requested the next internal readiness step.",
        )
        if task:
            task.update({
                "lane": "voice-bridge",
                "approval_boundary": "Do not enable live calls, provider credentials, or production routing.",
            })
            candidates.append(task)
    tasks = [task for task in candidates if task]
    if write:
        pending = TASK_ROOT / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        for task in tasks:
            write_json(pending / f"{task['id']}.json", task)
    return tasks


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# JVT AI Director",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Local model available: `{report['local_model'].get('available')}`",
        f"- Model router OK: `{((report.get('snapshot') or {}).get('model_router') or {}).get('ok')}`",
        f"- Ops DB OK: `{((report.get('snapshot') or {}).get('ops_db') or {}).get('ok')}`",
        f"- Codex escalation OK: `{((report.get('snapshot') or {}).get('codex_escalation') or {}).get('ok')}`",
        f"- Safety boundary: {report['safety_boundary']}",
        "",
        "## Directives",
        "",
    ]
    for item in report.get("directives", []):
        lines.append(f"- P{item.get('priority')} `{item.get('lane')}`: {item.get('action')}")
    lines.extend(["", "## Seeded Tasks", ""])
    for task in report.get("seeded_tasks", []):
        lines.append(f"- `{task.get('id')}` -> `{task.get('type')}`")
    if not report.get("seeded_tasks"):
        lines.append("- No new tasks seeded; existing tasks already cover today's directives.")
    lines.extend(["", "## Local Model Note", ""])
    if report["local_model"].get("available"):
        lines.append(report["local_model"].get("response") or "- Model returned no text.")
    else:
        lines.append(f"- {report['local_model'].get('reason')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="JVT AI Director: local-model-aware next-action manager.")
    parser.add_argument("--write-tasks", action="store_true")
    args = parser.parse_args()

    snapshot = build_snapshot()
    directives = deterministic_directives(snapshot)
    prompt = (
        "You are the local JVT AI Director. Review this machine state and propose only safe next actions. "
        "Do not recommend random mass email, spending, live trading, wallets, mining, staking, applications, or external commitments. "
        "Return concise operational guidance in 6 bullets or fewer. "
        f"State JSON: {json.dumps(snapshot, sort_keys=True)[:6000]}"
    )
    local_model = local_model_generate(prompt)
    seeded_tasks = seed_director_tasks(directives, write=args.write_tasks)
    report = {
        "generated_at": utc_now(),
        "mode": "local-llm-assisted" if local_model.get("available") else "deterministic-fallback",
        "snapshot": snapshot,
        "directives": directives,
        "seeded_tasks": seeded_tasks,
        "local_model": local_model,
        "safety_boundary": "May seed internal allowlisted tasks and recommend quality-gated sends. Must not spend, trade live, create wallets, mine, stake, submit applications, post publicly, or send outside approved outreach caps and gates.",
    }
    write_json(STATE_ROOT / "latest-ai-director.json", report)
    write_markdown(report, STATE_ROOT / "latest-ai-director.md")
    print(json.dumps({
        "mode": report["mode"],
        "directives": len(directives),
        "seeded_tasks": len(seeded_tasks),
        "local_model_available": local_model.get("available"),
        "json_path": str(STATE_ROOT / "latest-ai-director.json"),
        "markdown_path": str(STATE_ROOT / "latest-ai-director.md"),
    }, indent=2))


if __name__ == "__main__":
    main()
