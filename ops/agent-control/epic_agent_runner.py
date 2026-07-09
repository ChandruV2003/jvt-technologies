#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
EPIC_ROOT = CONTROL_ROOT / "epics"
STATE_ROOT = CONTROL_ROOT / "state"
LOCK_PATH = STATE_ROOT / "epic-agent.lock"
POLICY_PATH = CONTROL_ROOT / "policies" / "epic-agent-policy.json"
USAGE_LOG_PATH = STATE_ROOT / "epic-agent-usage.jsonl"
CODEX_CLI = Path("/Applications/Codex.app/Contents/Resources/codex")

EPIC_DIRS = ("queued", "running", "done", "blocked", "held", "logs", "architect-inbox")

FORBIDDEN_DIRECTIVES = {
    "send prospect email",
    "send email now",
    "contact third party",
    "submit application",
    "register sam.gov",
    "move funds",
    "transfer funds",
    "place live trade",
    "alpaca live",
    "create wallet",
    "mine crypto",
    "stake crypto",
    "post to instagram",
    "post to youtube",
    "publish now",
    "buy hardware",
    "purchase hardware",
    "pay for",
    "delete repository",
    "rm -rf",
}

SAFETY_BOUNDARY = (
    "No spending, prospect sends, public posting, applications, account changes, "
    "live trades, fund movement, wallets, mining, staking, or external commitments."
)

DEFAULT_POLICY = {
    "codex_cli_enabled": True,
    "max_codex_epics_per_day": 1,
    "min_seconds_between_codex_epics": 21600,
    "require_roi_case_for_codex_epics": True,
    "required_roi_fields": [
        "revenue_goal_link",
        "expected_business_value",
        "why_codex_is_worth_it",
        "success_metric",
        "fallback_if_not_run",
    ],
    "prefer_local_for_small_tasks": True,
    "local_first_note": (
        "Use ops/agent-control/tasks and local deterministic/model agents for small recurring work. "
        "Reserve Codex CLI for large queued epics only."
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    for folder in EPIC_DIRS:
        (EPIC_ROOT / folder).mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_policy() -> dict[str, Any]:
    policy = {**DEFAULT_POLICY, **load_json(POLICY_PATH, {})}
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not POLICY_PATH.exists():
        write_json(POLICY_PATH, policy)
    return policy


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def usage_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if USAGE_LOG_PATH.exists():
        for line in USAGE_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    for folder in ("done", "blocked"):
        for path in (EPIC_ROOT / folder).glob("*.json"):
            payload = load_json(path, {})
            result = payload.get("epic_agent_result") or {}
            mode = str(result.get("mode") or payload.get("execution_mode") or "")
            if not mode.startswith("codex"):
                continue
            finished_at = payload.get("epic_agent_updated_at")
            if not finished_at:
                continue
            events.append({
                "epic_id": payload.get("id") or path.stem,
                "mode": mode,
                "finished_at": finished_at,
                "source": str(path),
            })
    return events


def codex_budget_status(policy: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    events = usage_events()
    today_events = [
        event for event in events
        if (parse_time(event.get("finished_at")) or now).astimezone(timezone.utc).date().isoformat() == today
    ]
    latest_event = None
    latest_time = None
    for event in events:
        event_time = parse_time(event.get("finished_at"))
        if event_time and (latest_time is None or event_time > latest_time):
            latest_time = event_time
            latest_event = event
    seconds_since_latest = int((now - latest_time).total_seconds()) if latest_time else None
    max_per_day = int(policy.get("max_codex_epics_per_day") or 0)
    min_gap = int(policy.get("min_seconds_between_codex_epics") or 0)
    reasons: list[str] = []
    if not policy.get("codex_cli_enabled", True):
        reasons.append("Codex CLI epic execution disabled by policy.")
    if max_per_day and len(today_events) >= max_per_day:
        reasons.append(f"Daily Codex epic cap reached: {len(today_events)}/{max_per_day}.")
    if latest_time and min_gap and seconds_since_latest is not None and seconds_since_latest < min_gap:
        remaining = min_gap - seconds_since_latest
        reasons.append(f"Codex epic cooldown active for another {remaining} seconds.")
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "today": today,
        "today_codex_epics": len(today_events),
        "max_codex_epics_per_day": max_per_day,
        "min_seconds_between_codex_epics": min_gap,
        "seconds_since_latest_codex_epic": seconds_since_latest,
        "latest_codex_epic": latest_event,
    }


def roi_case_status(epic: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    mode = str(epic.get("execution_mode") or "")
    if not mode.startswith("codex") or not policy.get("require_roi_case_for_codex_epics", True):
        return {"required": False, "ok": True, "missing_fields": []}
    roi_case = epic.get("roi_case") if isinstance(epic.get("roi_case"), dict) else {}
    required = policy.get("required_roi_fields") if isinstance(policy.get("required_roi_fields"), list) else []
    missing = [field for field in required if not str(roi_case.get(field) or "").strip()]
    return {
        "required": True,
        "ok": not missing,
        "missing_fields": missing,
        "roi_case": roi_case,
    }


def append_usage_event(epic: dict[str, Any], result: dict[str, Any]) -> None:
    if not str(result.get("mode") or "").startswith("codex"):
        return
    USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "epic_id": epic.get("id"),
        "mode": result.get("mode"),
        "status": result.get("status"),
        "ok": result.get("ok"),
        "duration_ms": result.get("duration_ms"),
        "finished_at": utc_now(),
        "roi_case": epic.get("roi_case") if isinstance(epic.get("roi_case"), dict) else {},
    }
    with USAGE_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def count_files(folder: str) -> int:
    path = EPIC_ROOT / folder
    return sum(1 for item in path.glob("*.json") if item.is_file()) if path.exists() else 0


def epic_text(epic: dict[str, Any]) -> str:
    return json.dumps(epic, sort_keys=True).lower()


def hold_reason(epic: dict[str, Any]) -> str | None:
    if epic.get("requires_approval"):
        return "Epic declares requires_approval=true."
    if not epic.get("codex_enabled", True):
        return "Epic declares codex_enabled=false."
    direct_action_payload = {
        "requested_external_actions": epic.get("requested_external_actions") or [],
        "operator_directives": epic.get("operator_directives") or "",
        "unsafe_actions": epic.get("unsafe_actions") or [],
    }
    text = json.dumps(direct_action_payload, sort_keys=True).lower()
    for phrase in sorted(FORBIDDEN_DIRECTIVES):
        if phrase in text:
            return f"Epic contains approval-gated direct-action phrase: {phrase}"
    mode = str(epic.get("execution_mode") or "")
    if mode.startswith("codex") and not CODEX_CLI.exists():
        return f"Codex CLI missing at {CODEX_CLI}."
    return None


def move_epic(path: Path, target_dir: str, result: dict[str, Any]) -> Path:
    payload = load_json(path, {})
    payload["epic_agent_result"] = result
    payload["epic_agent_updated_at"] = utc_now()
    write_json(path, payload)
    target = EPIC_ROOT / target_dir / path.name
    if target.exists():
        target = target.with_name(f"{target.stem}-{int(time.time())}{target.suffix}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return target


def build_prompt(epic: dict[str, Any], log_dir: Path) -> str:
    scope_paths = epic.get("scope_paths") or []
    acceptance = epic.get("acceptance_criteria") or []
    deliverables = epic.get("deliverables") or []
    architect_policy = epic.get("architect_callback_policy") or (
        "If blocked or uncertain, write a concise question into the final answer. "
        "The epic runner stores the answer in architect-inbox for the solution architect."
    )
    lines = [
        "You are the JVT Epic Implementation Agent running unattended on the M4 Mac mini.",
        "",
        "Operating rule: do the largest safe amount of internal implementation work possible,",
        "but stop before any external, financial, account, or public action.",
        "",
        f"Hard safety boundary: {SAFETY_BOUNDARY}",
        "",
        "You may read and edit files inside this repository only. Do not send email,",
        "post content, contact third parties, move funds, trade live, mine, stake, create",
        "wallets, submit applications, buy anything, or make external commitments.",
        "",
        f"Repository: {REPO_ROOT}",
        f"Log directory for this run: {log_dir}",
        "",
        f"Epic ID: {epic.get('id')}",
        f"Title: {epic.get('title')}",
        "",
        "Story:",
        str(epic.get("story") or "").strip(),
        "",
        "Scope paths:",
    ]
    lines.extend(f"- {item}" for item in scope_paths)
    lines.extend(["", "Deliverables:"])
    lines.extend(f"- {item}" for item in deliverables)
    lines.extend(["", "Acceptance criteria:"])
    lines.extend(f"- {item}" for item in acceptance)
    roi_case = epic.get("roi_case") if isinstance(epic.get("roi_case"), dict) else {}
    if roi_case:
        lines.extend(["", "ROI case for using Codex credits:"])
        for key, value in roi_case.items():
            lines.append(f"- {key}: {value}")
    lines.extend([
        "",
        "Architect callback policy:",
        architect_policy,
        "",
        "Final response requirements:",
        "- Summarize what changed.",
        "- List validation performed.",
        "- List files created or changed.",
        "- If blocked, start the final answer with BLOCKED and state the exact question.",
        "- If no code/file edits are appropriate, produce the strongest implementation plan and explain why.",
        "",
    ])
    return "\n".join(lines)


def write_architect_inbox(epic: dict[str, Any], status: str, body: str, artifacts: list[str]) -> Path:
    inbox_path = EPIC_ROOT / "architect-inbox" / f"{epic.get('id', 'unknown')}-{status}.md"
    lines = [
        f"# Architect Handoff: {epic.get('title') or epic.get('id')}",
        "",
        f"- Generated: `{utc_now()}`",
        f"- Epic ID: `{epic.get('id')}`",
        f"- Status: `{status}`",
        "",
        "## Agent Output",
        "",
        body.strip() or "No final message captured.",
        "",
        "## Artifacts",
        "",
    ]
    if artifacts:
        lines.extend(f"- `{item}`" for item in artifacts)
    else:
        lines.append("- No artifacts recorded.")
    lines.append("")
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    inbox_path.write_text("\n".join(lines), encoding="utf-8")
    return inbox_path


def run_codex(epic: dict[str, Any], running_path: Path) -> dict[str, Any]:
    mode = str(epic.get("execution_mode") or "codex_readonly_plan")
    sandbox = "read-only" if mode == "codex_readonly_plan" else "workspace-write"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    epic_id = str(epic.get("id") or running_path.stem)
    log_dir = EPIC_ROOT / "logs" / f"{timestamp}-{epic_id}"
    log_dir.mkdir(parents=True, exist_ok=True)

    prompt = build_prompt(epic, log_dir)
    prompt_path = log_dir / "prompt.md"
    stdout_path = log_dir / "codex-events.jsonl"
    stderr_path = log_dir / "codex-stderr.log"
    last_message_path = log_dir / "last-message.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    command = [
        str(CODEX_CLI),
        "exec",
        "--cd",
        str(REPO_ROOT),
        "--sandbox",
        sandbox,
        "--json",
        "-o",
        str(last_message_path),
        "-",
    ]
    model = epic.get("model")
    if model:
        command[2:2] = ["-m", str(model)]
    profile = epic.get("profile")
    if profile:
        command[2:2] = ["-p", str(profile)]

    timeout = int(epic.get("timeout_seconds") or 1800)
    started = time.time()
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            cwd=str(REPO_ROOT),
            stdout=stdout_handle,
            stderr=stderr_handle,
            timeout=timeout,
            check=False,
        )
    duration_ms = int((time.time() - started) * 1000)
    last_message = last_message_path.read_text(encoding="utf-8", errors="ignore") if last_message_path.exists() else ""
    status = "blocked" if last_message.strip().startswith("BLOCKED") else ("done" if result.returncode == 0 else "blocked")
    inbox = write_architect_inbox(
        epic,
        status,
        last_message,
        [str(prompt_path), str(stdout_path), str(stderr_path), str(last_message_path)],
    )
    return {
        "ok": result.returncode == 0 and status == "done",
        "status": status,
        "returncode": result.returncode,
        "duration_ms": duration_ms,
        "mode": mode,
        "sandbox": sandbox,
        "log_dir": str(log_dir),
        "prompt_path": str(prompt_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "last_message_path": str(last_message_path),
        "architect_inbox_path": str(inbox),
    }


def run_architect_brief(epic: dict[str, Any]) -> dict[str, Any]:
    body = "\n".join([
        "This epic is queued as an architect brief, not a Codex execution run.",
        "",
        "Recommended next action:",
        str(epic.get("recommended_next_action") or "Convert this into one codex_workspace_write epic or smaller child epics."),
        "",
        "Story:",
        str(epic.get("story") or "").strip(),
    ])
    inbox = write_architect_inbox(epic, "briefed", body, [])
    return {"ok": True, "status": "done", "mode": "architect_brief", "architect_inbox_path": str(inbox)}


def process_epic(path: Path) -> dict[str, Any]:
    epic = load_json(path, {})
    epic_id = epic.get("id") or path.stem
    base = {"epic_file": str(path), "epic_id": epic_id, "execution_mode": epic.get("execution_mode")}
    reason = hold_reason(epic)
    if reason:
        held_path = move_epic(path, "held", {**base, "ok": False, "held": True, "reason": reason})
        return {**base, "status": "held", "path": str(held_path), "reason": reason}
    mode = str(epic.get("execution_mode") or "architect_brief")
    policy = load_policy()
    budget = codex_budget_status(policy)
    roi = roi_case_status(epic, policy)
    if mode.startswith("codex") and not roi["ok"]:
        return {
            **base,
            "status": "deferred",
            "ok": True,
            "path": str(path),
            "reason": f"Missing Codex ROI case fields: {', '.join(roi['missing_fields'])}",
            "roi_case": roi,
        }
    if mode.startswith("codex") and not budget["allowed"]:
        return {
            **base,
            "status": "deferred",
            "ok": True,
            "path": str(path),
            "reason": "; ".join(budget["reasons"]),
            "budget": budget,
        }

    running_path = EPIC_ROOT / "running" / path.name
    if running_path.exists():
        running_path = running_path.with_name(f"{running_path.stem}-{int(time.time())}{running_path.suffix}")
    shutil.move(str(path), str(running_path))
    write_running_state(epic, running_path)

    try:
        if mode == "architect_brief":
            result = run_architect_brief(epic)
        elif mode in {"codex_readonly_plan", "codex_workspace_write"}:
            result = run_codex(epic, running_path)
        else:
            result = {"ok": False, "status": "blocked", "reason": f"Unsupported execution_mode: {mode}"}
        append_usage_event(epic, result)
        target = "done" if result.get("ok") else "blocked"
        final_path = move_epic(running_path, target, {**base, **result})
        return {**base, "status": target, "path": str(final_path), "ok": bool(result.get("ok")), "result": result}
    except subprocess.TimeoutExpired as exc:
        inbox = write_architect_inbox(epic, "blocked", f"BLOCKED: Codex run timed out: {exc}", [])
        final_path = move_epic(running_path, "blocked", {**base, "ok": False, "error": f"Timed out: {exc}", "architect_inbox_path": str(inbox)})
        return {**base, "status": "blocked", "path": str(final_path), "error": f"Timed out: {exc}"}
    except Exception as exc:
        inbox = write_architect_inbox(epic, "blocked", f"BLOCKED: Epic runner exception: {exc!r}", [])
        final_path = move_epic(running_path, "blocked", {**base, "ok": False, "error": repr(exc), "architect_inbox_path": str(inbox)})
        return {**base, "status": "blocked", "path": str(final_path), "error": repr(exc)}


def run_queued(max_epics: int) -> dict[str, Any]:
    ensure_dirs()
    policy = load_policy()
    budget = codex_budget_status(policy)
    queued = sorted((EPIC_ROOT / "queued").glob("*.json"))[:max_epics]
    processed = [process_epic(path) for path in queued]
    return {
        "generated_at": utc_now(),
        "ok": all(item.get("status") in {"done", "deferred"} for item in processed) if processed else True,
        "processed_count": len(processed),
        "processed": processed,
        "queue_counts": {folder: count_files(folder) for folder in ("queued", "running", "done", "blocked", "held")},
        "codex_cli": str(CODEX_CLI),
        "codex_cli_exists": CODEX_CLI.exists(),
        "policy": policy,
        "codex_budget": budget,
        "roi_policy": {
            "require_roi_case_for_codex_epics": policy.get("require_roi_case_for_codex_epics"),
            "required_roi_fields": policy.get("required_roi_fields"),
        },
        "safety_boundary": SAFETY_BOUNDARY,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# JVT Epic Agent Runner",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Overall: `{'ok' if report.get('ok') else 'attention'}`",
        f"- Processed: `{report.get('processed_count')}`",
        f"- Safety: {report.get('safety_boundary')}",
        f"- Codex CLI exists: `{report.get('codex_cli_exists')}`",
        f"- Codex budget allowed: `{(report.get('codex_budget') or {}).get('allowed')}`",
        f"- Codex epics today: `{(report.get('codex_budget') or {}).get('today_codex_epics')}` / `{(report.get('codex_budget') or {}).get('max_codex_epics_per_day')}`",
        f"- ROI case required: `{(report.get('roi_policy') or {}).get('require_roi_case_for_codex_epics')}`",
        "",
        "## Queue Counts",
        "",
    ]
    for folder, count in (report.get("queue_counts") or {}).items():
        lines.append(f"- `{folder}`: {count}")
    lines.extend(["", "## Processed Epics", ""])
    if report.get("processed"):
        for item in report["processed"]:
            suffix = f": {item.get('reason')}" if item.get("status") == "deferred" and item.get("reason") else ""
            lines.append(f"- `{item.get('status')}` {item.get('epic_id')} ({item.get('execution_mode')}){suffix}")
    else:
        lines.append("- No queued epics were available.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_running_state(epic: dict[str, Any], running_path: Path) -> None:
    report = {
        "generated_at": utc_now(),
        "ok": True,
        "processed_count": 0,
        "processed": [],
        "active": {
            "epic_id": epic.get("id") or running_path.stem,
            "title": epic.get("title"),
            "execution_mode": epic.get("execution_mode"),
            "running_path": str(running_path),
            "started_at": utc_now(),
        },
        "queue_counts": {folder: count_files(folder) for folder in ("queued", "running", "done", "blocked", "held")},
        "codex_cli": str(CODEX_CLI),
        "codex_cli_exists": CODEX_CLI.exists(),
        "safety_boundary": SAFETY_BOUNDARY,
    }
    json_path = STATE_ROOT / "latest-epic-agent.json"
    markdown_path = STATE_ROOT / "latest-epic-agent.md"
    write_json(json_path, report)
    lines = [
        "# JVT Epic Agent Runner",
        "",
        f"- Generated: `{report['generated_at']}`",
        "- Overall: `running`",
        f"- Active epic: `{report['active']['epic_id']}`",
        f"- Mode: `{report['active']['execution_mode']}`",
        f"- Safety: {SAFETY_BOUNDARY}",
        "",
    ]
    markdown_path.write_text("\n".join(lines), encoding="utf-8")


def acquire_lock() -> int:
    ensure_dirs()
    try:
        return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - LOCK_PATH.stat().st_mtime if LOCK_PATH.exists() else 0
        if age > 7200:
            LOCK_PATH.unlink(missing_ok=True)
            return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        raise SystemExit("Epic agent is already running.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run queued JVT epic stories through the bounded epic agent.")
    parser.add_argument("--max-epics", type=int, default=1)
    args = parser.parse_args()

    lock_fd = acquire_lock()
    try:
        os.write(lock_fd, str(os.getpid()).encode("utf-8"))
        report = run_queued(max(1, args.max_epics))
        json_path = STATE_ROOT / "latest-epic-agent.json"
        markdown_path = STATE_ROOT / "latest-epic-agent.md"
        write_json(json_path, report)
        write_markdown(report, markdown_path)
        print(json.dumps({"ok": report["ok"], "processed_count": report["processed_count"], "json_path": str(json_path)}))
        if not report["ok"]:
            raise SystemExit(1)
    finally:
        os.close(lock_fd)
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
