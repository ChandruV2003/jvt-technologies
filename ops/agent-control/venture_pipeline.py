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
PIPELINE_PATH = REPO_ROOT / "strategy" / "venture-pipeline.json"


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


def score_opportunity(item: dict[str, Any], weights: dict[str, float]) -> float:
    scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
    total = 0.0
    for key, weight in weights.items():
        total += float(scores.get(key) or 0) * float(weight)
    return round(total, 2)


def approval_intensity(item: dict[str, Any]) -> str:
    actions = item.get("approval_required_actions")
    count = len(actions) if isinstance(actions, list) else 0
    scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
    approval_load = int(scores.get("approval_load") or 0)
    if approval_load >= 5 or count >= 3:
        return "high"
    if approval_load >= 3 or count:
        return "medium"
    return "low"


def can_advance_without_approval(item: dict[str, Any]) -> bool:
    actions = item.get("low_risk_next_actions")
    return bool(actions and isinstance(actions, list))


def normalized_opportunities(payload: dict[str, Any]) -> list[dict[str, Any]]:
    weights = payload.get("score_weights") if isinstance(payload.get("score_weights"), dict) else {}
    results: list[dict[str, Any]] = []
    for item in payload.get("opportunities") or []:
        if not isinstance(item, dict):
            continue
        result = dict(item)
        result["score"] = score_opportunity(item, weights)
        result["approval_intensity"] = approval_intensity(item)
        result["can_advance_without_approval"] = can_advance_without_approval(item)
        results.append(result)
    return sorted(results, key=lambda row: float(row.get("score") or 0), reverse=True)


def build_work_items(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for rank, item in enumerate(opportunities[:8], start=1):
        low_risk_actions = item.get("low_risk_next_actions") if isinstance(item.get("low_risk_next_actions"), list) else []
        approval_actions = item.get("approval_required_actions") if isinstance(item.get("approval_required_actions"), list) else []
        if low_risk_actions:
            items.append({
                "priority": rank,
                "opportunity_id": item.get("id"),
                "opportunity": item.get("name"),
                "category": item.get("category"),
                "automation_level": "stage-only",
                "title": f"Advance {item.get('name')}",
                "recommended_action": low_risk_actions[0],
                "approval_required_before": approval_actions,
            })
        elif approval_actions:
            items.append({
                "priority": rank,
                "opportunity_id": item.get("id"),
                "opportunity": item.get("name"),
                "category": item.get("category"),
                "automation_level": "approval-required",
                "title": f"Decision needed for {item.get('name')}",
                "recommended_action": item.get("next_validation_step") or approval_actions[0],
                "approval_required_before": approval_actions,
            })
    return items


def summarize_pipeline(payload: dict[str, Any], opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [item for item in opportunities if item.get("status") == "primary"]
    active = [item for item in opportunities if str(item.get("status") or "").startswith("active")]
    research = [item for item in opportunities if "research" in str(item.get("status") or "")]
    high_approval = [item for item in opportunities if item.get("approval_intensity") == "high"]
    return {
        "goal": payload.get("goal"),
        "operating_model": payload.get("operating_model"),
        "opportunity_count": len(opportunities),
        "primary_count": len(primary),
        "active_research_count": len(active),
        "research_count": len(research),
        "high_approval_count": len(high_approval),
        "top_opportunity": opportunities[0].get("name") if opportunities else "",
        "top_score": opportunities[0].get("score") if opportunities else None,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# JVT Venture Pipeline Report",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Goal: {report.get('summary', {}).get('goal')}",
        f"- Safety: {report.get('safety_boundary')}",
        "",
        "## Ranked Opportunities",
        "",
    ]
    for item in report.get("ranked_opportunities", [])[:8]:
        lines.append(
            f"- `{item.get('score')}` {item.get('name')} ({item.get('status')}, {item.get('category')}) - "
            f"{item.get('next_validation_step')}"
        )
    lines.extend(["", "## Next Autonomous Work", ""])
    for item in report.get("work_items", [])[:8]:
        lines.append(
            f"- P{item.get('priority')} `{item.get('automation_level')}` {item.get('title')}: "
            f"{item.get('recommended_action')}"
        )
    lines.extend(["", "## Approval Gates", ""])
    for line in report.get("red_lines", []):
        lines.append(f"- {line}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_report() -> dict[str, Any]:
    payload = load_json(PIPELINE_PATH, {})
    if not isinstance(payload, dict):
        payload = {}
    opportunities = normalized_opportunities(payload)
    report = {
        "generated_at": utc_now(),
        "status": "ready" if opportunities else "attention",
        "source_path": str(PIPELINE_PATH),
        "summary": summarize_pipeline(payload, opportunities),
        "ranked_opportunities": opportunities,
        "work_items": build_work_items(opportunities),
        "red_lines": payload.get("red_lines") or [],
        "sources": payload.get("sources") or [],
        "safety_boundary": "Research, scoring, drafting, and internal prep only. No spending, sends, applications, live trades, wallets, mining, staking, or external commitments.",
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the JVT venture pipeline report.")
    parser.add_argument("--state-dir", type=Path, default=STATE_ROOT)
    args = parser.parse_args()

    report = build_report()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.state_dir / "latest-venture-pipeline.json"
    markdown_path = args.state_dir / "latest-venture-pipeline.md"
    write_json(json_path, report)
    write_markdown(report, markdown_path)
    print(json.dumps({
        "ok": report["status"] == "ready",
        "status": report["status"],
        "work_items": len(report.get("work_items") or []),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }))


if __name__ == "__main__":
    main()
