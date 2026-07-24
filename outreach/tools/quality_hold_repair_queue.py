#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auto_approve_review_followups import rejection_reasons as followup_rejection_reasons
from auto_approve_review_initials import is_followup, rejection_reasons as initial_rejection_reasons
from recipient_quality import evidence_gate, lead_payload


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
QUEUE_ROOT = ROOT / "outreach" / "queue"
REVIEW = QUEUE_ROOT / "review"
STATE_ROOT = ROOT / "ops" / "agent-control" / "state"
STRATEGY_ROOT = ROOT / "strategy" / "prospect-packet-prep"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_slug() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def compact(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def repair_next_step(reasons: list[str]) -> str:
    joined = " | ".join(reasons).lower()
    if "existing quality hold" in joined:
        return "Review whether the old quality_hold_reason is still valid. Clear or replace it only if current source evidence proves the hold is stale."
    if "missing rendered message artifact" in joined:
        return "Regenerate the review packet render artifacts before approval can be considered."
    if "domain does not match" in joined:
        return "Find a matching public business inbox on the company domain or manually verify the off-domain contact source."
    if "generic/page-title" in joined or "company name too long" in joined:
        return "Repair the company identity from a public source, then rerun quality gates; reject if it is a directory/page-title lead."
    if "blocked recipient" in joined or "careers" in joined or "recruiting" in joined:
        return "Replace the recipient with an owner, partner, operations, intake, office, or public business inbox before approval."
    if "off-target" in joined or "software" in joined:
        return "Reject or reclassify; this is likely not a buyer for the current service lane."
    if "missing public source" in joined or "invalid recipient" in joined:
        return "Do not approve. Re-research the company/contact from a public source first."
    return "Manually review the listed blocker and repair the underlying packet before any approval."


def analyze_packet(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    followup = is_followup(payload)
    auto_reasons = followup_rejection_reasons(payload) if followup else initial_rejection_reasons(payload)
    shared_reasons, evidence = evidence_gate(lead_payload(payload))
    artifacts = {
        key: bool(payload.get(key) and Path(str(payload.get(key))).exists())
        for key in ("review_path", "text_path", "html_path")
    }
    if not auto_reasons and not shared_reasons:
        bucket = "approval_candidate"
    elif not shared_reasons and auto_reasons:
        bucket = "repair_candidate"
    elif shared_reasons:
        bucket = "hard_hold"
    else:
        bucket = "review"
    return {
        "stem": path.stem,
        "packet_path": str(path),
        "kind": "followup" if followup else "initial",
        "bucket": bucket,
        "company_name": payload.get("company_name"),
        "recipient_email": payload.get("recipient_email") or payload.get("public_email"),
        "industry": payload.get("industry"),
        "subject": payload.get("subject"),
        "contact_page": payload.get("contact_page") or payload.get("website"),
        "auto_approval_reasons": auto_reasons,
        "shared_gate_reasons": shared_reasons,
        "recipient_evidence": evidence,
        "artifacts": artifacts,
        "quality_hold_reason": payload.get("quality_hold_reason"),
        "repair_next_step": repair_next_step(auto_reasons or shared_reasons),
    }


def build_report(limit: int) -> dict[str, Any]:
    packets = [analyze_packet(path) for path in sorted(REVIEW.glob("*.json"), key=lambda item: (item.stat().st_mtime, item.name))]
    buckets = Counter(str(item["bucket"]) for item in packets)
    reason_counts = Counter(
        reason
        for item in packets
        for reason in [*item.get("auto_approval_reasons", []), *item.get("shared_gate_reasons", [])]
    )
    approval_candidates = [item for item in packets if item["bucket"] == "approval_candidate"]
    repair_candidates = [item for item in packets if item["bucket"] == "repair_candidate"]
    hard_holds = [item for item in packets if item["bucket"] == "hard_hold"]
    return {
        "generated_at": utc_now(),
        "ok": True,
        "review_count": len(packets),
        "bucket_counts": dict(sorted(buckets.items())),
        "top_reasons": [{"reason": reason, "count": count} for reason, count in reason_counts.most_common(20)],
        "approval_candidates": approval_candidates[:limit],
        "repair_candidates": repair_candidates[:limit],
        "hard_holds": hard_holds[:limit],
        "approval_candidate_count": len(approval_candidates),
        "repair_candidate_count": len(repair_candidates),
        "hard_hold_count": len(hard_holds),
        "guardrail": "Read-only review queue diagnosis. No packet movement, approvals, sends, provider calls, spending, or external commitments.",
        "next_action": "Fix repair candidates first, then rerun strict auto-approval dry-run before any send-ready movement.",
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Quality Hold Repair Queue",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Review packets: `{report['review_count']}`",
        f"- Approval candidates: `{report['approval_candidate_count']}`",
        f"- Repair candidates: `{report['repair_candidate_count']}`",
        f"- Hard holds: `{report['hard_hold_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "## Top Reasons",
        "",
    ]
    for item in report.get("top_reasons", []):
        lines.append(f"- `{item['count']}` {item['reason']}")
    if not report.get("top_reasons"):
        lines.append("- None.")

    for title, key in (
        ("Approval Candidates", "approval_candidates"),
        ("Repair Candidates", "repair_candidates"),
        ("Hard Holds", "hard_holds"),
    ):
        lines.extend(["", f"## {title}", ""])
        items = report.get(key) if isinstance(report.get(key), list) else []
        if not items:
            lines.append("- None.")
            continue
        for index, item in enumerate(items, start=1):
            reasons = item.get("auto_approval_reasons") or item.get("shared_gate_reasons") or []
            lines.extend([
                f"### {index}. {compact(item.get('company_name'), 120)}",
                "",
                f"- Kind: `{item.get('kind')}`",
                f"- Packet: `{Path(str(item.get('packet_path'))).relative_to(ROOT)}`",
                f"- Recipient: `{item.get('recipient_email') or ''}`",
                f"- Industry: `{item.get('industry') or ''}`",
                f"- Subject: {compact(item.get('subject'), 160)}",
                f"- Source: {item.get('contact_page') or ''}",
                f"- Reasons: {', '.join(reasons) if reasons else 'none'}",
                f"- Next: {item.get('repair_next_step')}",
                "",
            ])
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or ""), ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a read-only queue of review packets that are blocked by stale or repairable quality holds.")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    report = build_report(max(1, args.limit))
    state_json = STATE_ROOT / "latest-quality-hold-repair-queue.json"
    state_md = STATE_ROOT / "latest-quality-hold-repair-queue.md"
    strategy_md = STRATEGY_ROOT / f"quality-hold-repair-queue-{today_slug()}.md"
    write_json(state_json, report)
    write_markdown(report, state_md)
    write_markdown(report, strategy_md)
    print(json.dumps({
        "ok": True,
        "review_count": report["review_count"],
        "approval_candidate_count": report["approval_candidate_count"],
        "repair_candidate_count": report["repair_candidate_count"],
        "hard_hold_count": report["hard_hold_count"],
        "state_json": str(state_json),
    }, indent=2))


if __name__ == "__main__":
    main()
