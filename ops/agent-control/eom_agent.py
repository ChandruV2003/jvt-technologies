#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
ORCHESTRATOR_STATE = STATE_ROOT / "latest-orchestrator.json"
VENTURE_STATE = STATE_ROOT / "latest-venture-pipeline.json"
GROWTH_CHECKIN_STATE = STATE_ROOT / "latest-growth-ops-checkin.json"
WATCHDOG_STATE = REPO_ROOT / "ops" / "watchdog" / "state" / "latest-watchdog.json"
INTEROP_STATE = STATE_ROOT / "latest-agent-interop.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def automation_level(item: dict[str, Any]) -> str:
    return str(item.get("automation_level") or "").strip().lower()


def priority(item: dict[str, Any]) -> int:
    try:
        return int(item.get("priority") or 99)
    except Exception:
        return 99


def split_work_items(work_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    autonomous: list[dict[str, Any]] = []
    approval: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in sorted(work_items, key=lambda row: (priority(row), str(row.get("lane") or ""), str(row.get("title") or ""))):
        if item.get("blocked_by"):
            blocked.append(item)
            continue
        level = automation_level(item)
        if level in {"stage-only", "autonomous", "autonomous-detection"}:
            autonomous.append(item)
        elif "approval" in level or "required" in level:
            approval.append(item)
        else:
            autonomous.append(item)
    return {"autonomous": autonomous, "approval": approval, "blocked": blocked}


def choose_focus(orchestrator: dict[str, Any], venture: dict[str, Any]) -> dict[str, Any]:
    work_items = orchestrator.get("work_items") if isinstance(orchestrator.get("work_items"), list) else []
    split = split_work_items([item for item in work_items if isinstance(item, dict)])
    venture_stage = [item for item in split["autonomous"] if item.get("lane") == "venture-growth"]
    if venture_stage:
        return {
            "mode": "autonomous-stage",
            "item": venture_stage[0],
            "reason": "Highest-priority concrete venture-growth item. Prefer this over vague service-wedge placeholders.",
        }
    if split["autonomous"]:
        return {
            "mode": "autonomous-stage",
            "item": split["autonomous"][0],
            "reason": "Highest-priority non-blocked stage-only work item.",
        }

    venture_items = venture.get("work_items") if isinstance(venture.get("work_items"), list) else []
    if venture_items:
        return {
            "mode": "venture-stage",
            "item": venture_items[0],
            "reason": "No orchestrator stage-only item was available; use top venture pipeline item.",
        }

    if split["approval"]:
        return {
            "mode": "approval-needed",
            "item": split["approval"][0],
            "reason": "Work is waiting on operator approval before it can safely advance.",
        }

    return {
        "mode": "monitor",
        "item": {},
        "reason": "No actionable work item was available in current state.",
    }


def build_report() -> dict[str, Any]:
    orchestrator = load_json(ORCHESTRATOR_STATE, {})
    venture = load_json(VENTURE_STATE, {})
    growth = load_json(GROWTH_CHECKIN_STATE, {})
    watchdog = load_json(WATCHDOG_STATE, {})
    interop = load_json(INTEROP_STATE, {})
    work_items = orchestrator.get("work_items") if isinstance(orchestrator.get("work_items"), list) else []
    split = split_work_items([item for item in work_items if isinstance(item, dict)])
    focus = choose_focus(orchestrator, venture)
    quotas = orchestrator.get("quotas") if isinstance(orchestrator.get("quotas"), dict) else {}

    blockers: list[str] = []
    if not watchdog.get("overall_ok", watchdog.get("ok", True)):
        blockers.append("watchdog-not-clear")
    if not interop.get("ok", True):
        blockers.append("agent-interop-not-clear")
    for item in split["blocked"]:
        blockers.append(str(item.get("title") or item.get("id") or "blocked-work-item"))

    report = {
        "generated_at": utc_now(),
        "status": "attention" if blockers else "ready",
        "focus": focus,
        "counts": {
            "work_items": len(work_items),
            "autonomous_stage_items": len(split["autonomous"]),
            "approval_items": len(split["approval"]),
            "blocked_items": len(split["blocked"]),
            "venture_work_items": len(venture.get("work_items") or []),
        },
        "send_gate": {
            "operator_send_ready": bool(quotas.get("operator_send_ready")),
            "approved_backlog": quotas.get("approved_backlog", 0),
            "review_backlog": quotas.get("review_backlog", 0),
            "eligible_followups": quotas.get("eligible_followups", 0),
            "ramp_recommendation": quotas.get("ramp_recommendation") or "",
        },
        "top_autonomous_items": split["autonomous"][:8],
        "approval_items": split["approval"][:8],
        "blockers": blockers,
        "inputs": {
            "orchestrator_generated_at": orchestrator.get("generated_at"),
            "venture_generated_at": venture.get("generated_at"),
            "growth_checkin_generated_at": growth.get("generated_at"),
            "watchdog_generated_at": watchdog.get("generated_at"),
            "interop_generated_at": interop.get("generated_at"),
        },
        "safety_boundary": "EOM may coordinate, rank, stage internal prep, and escalate decisions. Delegated email sending is handled only by the quality-gated auto-send runner within outbound caps; EOM itself must not spend, contact third parties outside approved outreach, submit applications, trade live, move funds, mine, stake, create wallets, or make commitments.",
    }
    return report


def write_markdown(report: dict[str, Any], path: Path) -> None:
    focus = report.get("focus") or {}
    item = focus.get("item") if isinstance(focus.get("item"), dict) else {}
    focus_action = item.get("recommended_action") or ""
    if str(focus_action).startswith("Turn this into") and item.get("detail"):
        focus_action = item.get("detail")
    lines = [
        "# JVT Executive Operations Manager Brief",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Mode: `{focus.get('mode')}`",
        f"- Safety: {report.get('safety_boundary')}",
        "",
        "## Current Focus",
        "",
        f"- Title: {item.get('title') or item.get('opportunity') or 'None'}",
        f"- Lane: `{item.get('lane') or item.get('category') or 'none'}`",
        f"- Recommended action: {focus_action or 'No action recorded.'}",
        f"- Why: {focus.get('reason')}",
        "",
        "## Send Gate",
        "",
    ]
    send_gate = report.get("send_gate") or {}
    lines.extend([
        f"- Operator send ready: `{send_gate.get('operator_send_ready')}`",
        f"- Approved backlog: `{send_gate.get('approved_backlog')}`",
        f"- Review backlog: `{send_gate.get('review_backlog')}`",
        f"- Eligible follow-ups: `{send_gate.get('eligible_followups')}`",
        f"- Recommendation: {send_gate.get('ramp_recommendation')}",
        "",
        "## Next Stage-Only Items",
        "",
    ])
    for action in report.get("top_autonomous_items", [])[:6]:
        lines.append(f"- P{action.get('priority')} `{action.get('lane')}` {action.get('title')} - {action.get('recommended_action')}")
    lines.extend(["", "## Approval Items", ""])
    approvals = report.get("approval_items") or []
    if approvals:
        for action in approvals[:6]:
            lines.append(f"- P{action.get('priority')} `{action.get('lane')}` {action.get('title')} - {action.get('recommended_action')}")
    else:
        lines.append("- No approval-only item is currently first in line.")
    lines.extend(["", "## Blockers", ""])
    blockers = report.get("blockers") or []
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- No EOM blockers detected.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the JVT Executive Operations Manager brief.")
    parser.add_argument("--state-dir", type=Path, default=STATE_ROOT)
    args = parser.parse_args()

    report = build_report()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.state_dir / "latest-eom-brief.json"
    markdown_path = args.state_dir / "latest-eom-brief.md"
    write_json(json_path, report)
    write_markdown(report, markdown_path)
    print(json.dumps({
        "ok": report["status"] == "ready",
        "status": report["status"],
        "mode": report["focus"]["mode"],
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }))


if __name__ == "__main__":
    main()
