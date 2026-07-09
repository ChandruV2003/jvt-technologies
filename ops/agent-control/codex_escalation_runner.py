#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
CONFIG_PATH = CONTROL_ROOT / "config" / "codex-escalation-policy.json"
STATE_PATH = CONTROL_ROOT / "state" / "latest-codex-escalation.json"
USAGE_LOG = CONTROL_ROOT / "logs" / "codex-escalation-usage.jsonl"
RUN_ROOT = CONTROL_ROOT / "state" / "codex-escalations"

DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "timezone": "America/New_York",
    "default_model": "gpt-5.5",
    "default_reasoning_effort": "medium",
    "default_sandbox": "read-only",
    "daily_caps": {
        "total_execute": 8,
        "gpt-5.5": 5,
        "high_or_xhigh": 2
    },
    "allowed_sandboxes": ["read-only", "workspace-write"],
    "allowed_models": ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"],
    "disallowed_phrases": [
        "send prospect email",
        "send email to prospect",
        "place live trade",
        "alpaca live",
        "move funds",
        "bank transfer",
        "create wallet",
        "stake crypto",
        "mine crypto",
        "submit application",
        "change payment",
        "stripe",
        "wire transfer"
    ],
    "notes": "Wrapper only. It does not execute Codex unless --execute is passed and all caps/policy checks pass."
}


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


def ensure_policy() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        write_json(CONFIG_PATH, DEFAULT_POLICY)
        return DEFAULT_POLICY
    current = load_json(CONFIG_PATH, {})
    merged = json.loads(json.dumps(DEFAULT_POLICY))
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def local_date(policy: dict[str, Any]) -> str:
    tz_name = str(policy.get("timezone") or "America/New_York")
    tz = timezone.utc
    if ZoneInfo:
        try:
            tz = ZoneInfo(tz_name)  # type: ignore[assignment]
        except Exception:
            tz = timezone.utc
    return datetime.now(tz).date().isoformat()


def codex_cli_path() -> str | None:
    candidates = [
        os.environ.get("JVT_CODEX_CLI", ""),
        "/Applications/Codex.app/Contents/Resources/codex",
        shutil.which("codex") or "",
    ]
    for item in candidates:
        if item and Path(item).exists():
            return item
    return None


def has_codex_auth() -> bool:
    if os.environ.get("CODEX_API_KEY"):
        return True
    return (Path.home() / ".codex" / "auth.json").exists()


def usage_rows() -> list[dict[str, Any]]:
    if not USAGE_LOG.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def usage_summary(policy: dict[str, Any]) -> dict[str, Any]:
    today = local_date(policy)
    rows = [row for row in usage_rows() if row.get("local_date") == today and row.get("executed")]
    by_model: dict[str, int] = {}
    high_or_xhigh = 0
    for row in rows:
        model = str(row.get("model") or "unknown")
        by_model[model] = by_model.get(model, 0) + 1
        if str(row.get("reasoning_effort") or "").lower() in {"high", "xhigh"}:
            high_or_xhigh += 1
    caps = policy.get("daily_caps") or {}
    return {
        "local_date": today,
        "executed_today": len(rows),
        "by_model": by_model,
        "high_or_xhigh_today": high_or_xhigh,
        "remaining": {
            "total_execute": max(0, int(caps.get("total_execute") or 0) - len(rows)),
            "gpt-5.5": max(0, int(caps.get("gpt-5.5") or 0) - by_model.get("gpt-5.5", 0)),
            "high_or_xhigh": max(0, int(caps.get("high_or_xhigh") or 0) - high_or_xhigh),
        },
    }


def contains_disallowed(prompt: str, policy: dict[str, Any]) -> str | None:
    lowered = prompt.lower()
    for phrase in policy.get("disallowed_phrases") or []:
        escaped = re.escape(str(phrase).lower()).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", lowered):
            return str(phrase)
    return None


def status_payload(policy: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "generated_at": utc_now(),
        "ok": bool(policy.get("enabled")) and bool(codex_cli_path()) and has_codex_auth(),
        "enabled": bool(policy.get("enabled")),
        "codex_cli": codex_cli_path(),
        "auth_present": has_codex_auth(),
        "policy": {
            "default_model": policy.get("default_model"),
            "default_reasoning_effort": policy.get("default_reasoning_effort"),
            "default_sandbox": policy.get("default_sandbox"),
            "daily_caps": policy.get("daily_caps"),
        },
        "usage": usage_summary(policy),
        "safety_boundary": "No execution unless --execute is supplied and policy/caps pass. External actions remain approval-gated.",
    }
    write_json(STATE_PATH, payload)
    return payload


def append_usage(row: dict[str, Any]) -> None:
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def cap_check(model: str, reasoning_effort: str, policy: dict[str, Any]) -> str | None:
    summary = usage_summary(policy)
    if summary["remaining"]["total_execute"] <= 0:
        return "daily total execute cap exhausted"
    if model == "gpt-5.5" and summary["remaining"]["gpt-5.5"] <= 0:
        return "daily gpt-5.5 cap exhausted"
    if reasoning_effort.lower() in {"high", "xhigh"} and summary["remaining"]["high_or_xhigh"] <= 0:
        return "daily high/xhigh cap exhausted"
    return None


def run_codex(args: argparse.Namespace, policy: dict[str, Any]) -> dict[str, Any]:
    model = args.model or str(policy.get("default_model") or "gpt-5.5")
    reasoning_effort = args.reasoning_effort or str(policy.get("default_reasoning_effort") or "medium")
    sandbox = args.sandbox or str(policy.get("default_sandbox") or "read-only")
    task_id = args.task_id or f"manual-{int(time.time())}"

    prompt = args.prompt or ""
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    prompt = prompt.strip()

    blockers: list[str] = []
    if not policy.get("enabled"):
        blockers.append("policy disabled")
    if not prompt:
        blockers.append("empty prompt")
    if model not in set(policy.get("allowed_models") or []):
        blockers.append(f"model not allowed: {model}")
    if sandbox not in set(policy.get("allowed_sandboxes") or []):
        blockers.append(f"sandbox not allowed: {sandbox}")
    if not codex_cli_path():
        blockers.append("codex cli missing")
    if not has_codex_auth():
        blockers.append("codex auth missing")
    blocked_phrase = contains_disallowed(prompt, policy)
    if blocked_phrase:
        blockers.append(f"prompt contains approval-gated phrase: {blocked_phrase}")
    cap_blocker = cap_check(model, reasoning_effort, policy)
    if args.execute and cap_blocker:
        blockers.append(cap_blocker)

    run_dir = RUN_ROOT / task_id
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    base_result: dict[str, Any] = {
        "generated_at": utc_now(),
        "task_id": task_id,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "sandbox": sandbox,
        "execute_requested": bool(args.execute),
        "executed": False,
        "ok": False,
        "blockers": blockers,
        "prompt_path": str(prompt_path),
    }
    if blockers:
        write_json(run_dir / "result.json", base_result)
        return base_result
    if not args.execute:
        base_result.update({"ok": True, "dry_run": True, "command_preview": "execution skipped; pass --execute to spend Codex credits"})
        write_json(run_dir / "result.json", base_result)
        return base_result

    output_path = run_dir / "codex-events.jsonl"
    command = [
        str(codex_cli_path()),
        "exec",
        "--json",
        "--model",
        model,
        "--sandbox",
        sandbox,
        "--skip-git-repo-check",
        prompt,
    ]
    started = time.time()
    with output_path.open("w", encoding="utf-8") as output:
        result = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            stdout=output,
            stderr=subprocess.PIPE,
            text=True,
            timeout=int(args.timeout_seconds),
            check=False,
        )
    elapsed_ms = int((time.time() - started) * 1000)
    base_result.update({
        "executed": True,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "duration_ms": elapsed_ms,
        "events_path": str(output_path),
        "stderr_tail": result.stderr.strip().splitlines()[-20:],
    })
    write_json(run_dir / "result.json", base_result)
    append_usage({
        "generated_at": utc_now(),
        "local_date": local_date(policy),
        "task_id": task_id,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "sandbox": sandbox,
        "executed": True,
        "ok": base_result["ok"],
        "duration_ms": elapsed_ms,
    })
    status_payload(policy)
    return base_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded Codex escalation runner for JVT.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--task-id")
    run_parser.add_argument("--prompt")
    run_parser.add_argument("--prompt-file")
    run_parser.add_argument("--model")
    run_parser.add_argument("--reasoning-effort")
    run_parser.add_argument("--sandbox")
    run_parser.add_argument("--timeout-seconds", type=int, default=900)
    run_parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    policy = ensure_policy()
    if args.command in {None, "status"}:
        print(json.dumps(status_payload(policy), indent=2))
        return
    if args.command == "run":
        result = run_codex(args, policy)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
