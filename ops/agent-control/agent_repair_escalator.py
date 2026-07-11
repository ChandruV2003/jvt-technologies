#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
TASK_ROOT = CONTROL_ROOT / "tasks"
EPIC_ROOT = CONTROL_ROOT / "epics"
REPAIR_ROOT = STATE_ROOT / "agent-repair"
REPORT_JSON = STATE_ROOT / "latest-agent-repair.json"
REPORT_MD = STATE_ROOT / "latest-agent-repair.md"

SAFE_AGENT_NAMES = {"egg", "local-task-runner", "ai-director", "growth-ops-checkin", "orchestrator"}


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


def tail_text(path: str | None, max_lines: int = 80) -> list[str]:
    if not path:
        return []
    item = Path(path)
    if not item.exists():
        return []
    return item.read_text(encoding="utf-8", errors="ignore").splitlines()[-max_lines:]


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def current_git_status() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return result.stdout.strip().splitlines()[:80]


def recent_failure_count(agent: str) -> int:
    if not REPAIR_ROOT.exists():
        return 0
    cutoff = time.time() - int(os.environ.get("JVT_REPAIR_WINDOW_SECONDS") or "3600")
    count = 0
    for path in REPAIR_ROOT.glob(f"{agent}-*.json"):
        if path.stat().st_mtime >= cutoff:
            payload = load_json(path, {})
            if payload.get("returncode") not in {None, 0, "0"}:
                count += 1
    return count


def model_repair_plan(context: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "You are the JVT internal repair planner. Return JSON only with keys: "
        "root_cause, likely_files, safest_fix_plan, validation_steps, escalation_needed. "
        "Use the failure context to propose internal repo repair steps. "
        "Do not propose external operations, account changes, provider enablement, public release, or financial activity. "
        f"Context JSON: {json.dumps(context, sort_keys=True)[:9000]}"
    )
    payload = json.dumps({
        "task_type": "strategy",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 700,
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:8760/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=75) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": str(exc)}
    choices = body.get("choices") if isinstance(body.get("choices"), list) else []
    message = ((choices[0] or {}).get("message") or {}) if choices else {}
    return {
        "available": True,
        "raw": str(message.get("content") or "").strip()[:5000],
        "router": body.get("jvt_router"),
    }


def codex_epic_for_failure(agent: str, context: dict[str, Any], model_plan: dict[str, Any]) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    epic_id = f"{today}-{agent}-agent-repair-{short_hash(json.dumps(context, sort_keys=True))}"
    epic_path = EPIC_ROOT / "queued" / f"{epic_id}.json"
    prompt_path = REPAIR_ROOT / f"{epic_id}-prompt.md"
    prompt_lines = [
        f"# JVT Agent Repair: {agent}",
        "",
        "Fix the failing internal automation path using the smallest safe repo change.",
        "",
        "Scope:",
        "- Inspect the failing agent, its runner wrapper, and the local task runner integration.",
        "- Patch only internal automation files needed for the failure.",
        "- Validate with compilation and a dry run where possible.",
        "- Do not perform external operations or account/provider actions.",
        "",
        "Failure context:",
        "",
        "```json",
        json.dumps(context, indent=2)[:12000],
        "```",
        "",
        "Local model repair plan:",
        "",
        "```json",
        json.dumps(model_plan, indent=2)[:8000],
        "```",
        "",
    ]
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("\n".join(prompt_lines), encoding="utf-8")

    mode = "codex_workspace_write" if os.environ.get("JVT_REPAIR_CODEX_WORKSPACE_WRITE") == "1" else "codex_readonly_plan"
    epic = {
        "id": epic_id,
        "title": f"Repair {agent} internal agent failure",
        "story": "A recurring internal agent failure was detected. Use the failure packet and local model plan to produce a minimal repair or a precise blocked handoff.",
        "execution_mode": mode,
        "model": os.environ.get("JVT_REPAIR_CODEX_MODEL") or "gpt-5.5",
        "scope_paths": [
            "ops/agent-control",
            "ops/watchdog",
            "outreach/tools",
        ],
        "deliverables": [
            "Minimal internal automation repair or precise blocked handoff",
            "Validation commands and results",
            "Updated state/report artifacts if applicable",
        ],
        "acceptance_criteria": [
            "The failing command no longer exits with the same error, or the blocker is captured with exact evidence.",
            "The repair stays inside internal automation scope.",
            "No external operations are performed.",
        ],
        "roi_case": {
            "revenue_goal_link": "Protects the autonomous JVT operating loop that supports the $10k target.",
            "expected_business_value": "Reduces operator intervention for broken background agents.",
            "why_codex_is_worth_it": "Use only after local repair planning records enough context or failures repeat.",
            "success_metric": "Agent health returns to ok and queue does not stall on the same failure.",
            "fallback_if_not_run": "Leave repair packet for the solution architect and keep local model report visible.",
        },
        "repair_prompt_path": str(prompt_path),
        "created_by": "agent_repair_escalator",
        "created_at": utc_now(),
        "requires_approval": False,
        "codex_enabled": True,
    }
    if not epic_path.exists():
        epic_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(epic_path, epic)
    return {"id": epic_id, "path": str(epic_path), "prompt_path": str(prompt_path), "execution_mode": mode}


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Agent Repair",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Agent: `{report.get('agent')}`",
        f"- Return code: `{report.get('returncode')}`",
        f"- Recent failures: `{report.get('recent_failure_count')}`",
        f"- Local model available: `{(report.get('model_plan') or {}).get('available')}`",
        f"- Codex epic queued: `{bool(report.get('codex_epic'))}`",
        "",
        "## Error Tail",
        "",
    ]
    stderr_tail = report.get("stderr_tail") or []
    if stderr_tail:
        lines.extend(f"- `{line[:220]}`" for line in stderr_tail[-12:])
    else:
        lines.append("- None.")
    lines.extend(["", "## Next", ""])
    if report.get("codex_epic"):
        lines.append("- A capped repair epic is queued for the higher-tier path.")
    else:
        lines.append("- Local repair analysis was captured; no capped epic was required yet.")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_context(args: argparse.Namespace) -> dict[str, Any]:
    stdout_tail = tail_text(args.stdout_file)
    stderr_tail = tail_text(args.stderr_file)
    latest_agent_state = load_json(STATE_ROOT / f"latest-{args.agent}-agent.json", {})
    return {
        "generated_at": utc_now(),
        "agent": args.agent,
        "command": args.command or "",
        "returncode": args.returncode,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "latest_agent_state": latest_agent_state,
        "git_status": current_git_status(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="JVT internal agent repair escalator.")
    parser.add_argument("--agent", default="egg")
    parser.add_argument("--returncode", type=int, default=1)
    parser.add_argument("--stdout-file")
    parser.add_argument("--stderr-file")
    parser.add_argument("--command")
    parser.add_argument("--force-epic", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    args.agent = str(args.agent or "egg").strip().lower()
    if args.agent not in SAFE_AGENT_NAMES:
        raise SystemExit(f"unsupported agent name: {args.agent}")

    context = build_context(args)
    model_plan = model_repair_plan(context)
    failure_count = recent_failure_count(args.agent) + (1 if args.returncode else 0)
    threshold = int(os.environ.get("JVT_REPAIR_CODEX_THRESHOLD") or "2")
    codex_epic = None
    if not args.dry_run and (args.force_epic or failure_count >= threshold):
        codex_epic = codex_epic_for_failure(args.agent, context, model_plan)

    repair_id = f"{args.agent}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{short_hash(json.dumps(context, sort_keys=True))}"
    repair_path = REPAIR_ROOT / f"{repair_id}.json"
    report = {
        **context,
        "repair_id": repair_id,
        "model_plan": model_plan,
        "recent_failure_count": failure_count,
        "codex_epic": codex_epic,
        "safety_boundary": "Internal repair triage only. External operations and account/provider actions remain out of scope.",
        "artifact_path": str(repair_path),
    }
    if not args.dry_run:
        write_json(repair_path, report)
        write_json(REPORT_JSON, report)
        write_markdown(report)
    print(json.dumps({
        "ok": True,
        "dry_run": args.dry_run,
        "agent": args.agent,
        "recent_failure_count": failure_count,
        "model_available": bool(model_plan.get("available")),
        "codex_epic": codex_epic,
        "json_path": str(REPORT_JSON),
        "markdown_path": str(REPORT_MD),
    }, indent=2))


if __name__ == "__main__":
    main()
