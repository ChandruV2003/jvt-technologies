#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packet_quality import classify_packet, clear_safe_historical_hold, stamp_packet_quality


ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "outreach" / "queue" / "review"
STATE_ROOT = ROOT / "ops" / "agent-control" / "state"
REPORT_JSON = STATE_ROOT / "latest-review-quality-hold-resolution.json"
REPORT_MD = STATE_ROOT / "latest-review-quality-hold-resolution.md"

GUARDRAIL = (
    "Review metadata repair only. This tool never approves or moves packets, sends outreach, "
    "calls providers, spends money, changes financial accounts, publishes, or makes external commitments."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def resolve_packet(path: Path, *, write: bool) -> dict[str, Any]:
    payload = load_json(path)
    if not payload:
        return {
            "stem": path.stem,
            "result": "held",
            "reason": "invalid queue metadata json",
            "written": False,
        }

    hold = str(payload.get("quality_hold_reason") or "").strip()
    result = classify_packet(payload, source_queue="review", strict_historical_hold=False)
    item = {
        "stem": path.stem,
        "company_name": payload.get("company_name"),
        "recipient_email": payload.get("recipient_email") or payload.get("public_email"),
        "decision": result["decision"],
        "reason_codes": result["reason_codes"],
        "human_reasons": result["human_reasons"],
        "historical_hold": hold,
        "historical_hold_only": result["historical_hold_only"],
        "safe_to_clear_quality_hold": result["safe_to_clear_quality_hold"],
        "written": False,
    }
    if not hold:
        item["result"] = "no_active_hold"
        return item
    if not result["safe_to_clear_quality_hold"]:
        item["result"] = "kept_current_hold"
        return item

    item["result"] = "would_clear" if not write else "cleared"
    if not write:
        return item

    clear_safe_historical_hold(payload, result, source="resolve_review_quality_holds")
    refreshed = classify_packet(payload, source_queue="review", strict_historical_hold=False)
    stamp_packet_quality(payload, refreshed)
    write_json(path, payload)
    item["written"] = True
    item["post_resolution_decision"] = refreshed["decision"]
    return item


def build_report(*, write: bool, limit: int) -> dict[str, Any]:
    results = [
        resolve_packet(path, write=write)
        for path in sorted(REVIEW.glob("*.json"), key=lambda item: (item.stat().st_mtime, item.name))
    ]
    safe = [item for item in results if item.get("safe_to_clear_quality_hold")]
    cleared = [item for item in results if item.get("result") == "cleared"]
    kept = [item for item in results if item.get("result") == "kept_current_hold"]
    return {
        "generated_at": utc_now(),
        "ok": True,
        "mode": "write" if write else "dry-run",
        "review_count": len(results),
        "active_hold_count": sum(1 for item in results if item.get("historical_hold")),
        "safe_to_clear_count": len(safe),
        "cleared_count": len(cleared),
        "kept_current_hold_count": len(kept),
        "results": results[:limit],
        "safe_to_clear": safe[:limit],
        "kept_current_hold": kept[:limit],
        "guardrail": GUARDRAIL,
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Review Quality Hold Resolution",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Review packets: `{report['review_count']}`",
        f"- Active holds: `{report['active_hold_count']}`",
        f"- Safe to clear: `{report['safe_to_clear_count']}`",
        f"- Cleared: `{report['cleared_count']}`",
        f"- Kept current: `{report['kept_current_hold_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "## Safe To Clear",
        "",
    ]
    for item in report.get("safe_to_clear", []):
        lines.append(
            f"- `{item['stem']}`: {item.get('historical_hold') or ''} "
            f"({item.get('result')}, written={item.get('written')})"
        )
    if not report.get("safe_to_clear"):
        lines.append("- None.")
    lines.extend(["", "## Kept Current", ""])
    for item in report.get("kept_current_hold", []):
        reasons = ", ".join(item.get("human_reasons") or [])
        lines.append(f"- `{item['stem']}`: {reasons or 'current classifier blocker'}")
    if not report.get("kept_current_hold"):
        lines.append("- None.")
    lines.append("")
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely preserve and clear stale review quality holds without approving or moving packets."
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    report = build_report(write=args.write, limit=max(1, args.limit))
    write_json(REPORT_JSON, report)
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": True,
                "mode": report["mode"],
                "review_count": report["review_count"],
                "active_hold_count": report["active_hold_count"],
                "safe_to_clear_count": report["safe_to_clear_count"],
                "cleared_count": report["cleared_count"],
                "kept_current_hold_count": report["kept_current_hold_count"],
                "report": str(REPORT_JSON),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
