#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from model_packet_reviewer import review_packet
from packet_quality import (
    classify_packet,
    clear_safe_historical_hold,
    is_auto_approval_candidate,
    stamp_packet_quality,
)


ROOT = Path(__file__).resolve().parents[2]
QUEUE_ROOT = ROOT / "outreach" / "queue"
REVIEW = QUEUE_ROOT / "review"
APPROVED = QUEUE_ROOT / "approved"
REPORT_DIR = ROOT / "outreach" / "schedules" / "followups"


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def queue_paths(stem: str, queue: Path) -> list[Path]:
    return sorted(queue.glob(f"{stem}.*"))


def is_followup(payload: dict[str, Any]) -> bool:
    return bool(payload.get("follow_up_stage") or payload.get("follow_up_parent_stem"))


def rejection_reasons(payload: dict[str, Any]) -> list[str]:
    result = classify_packet(payload, source_queue="review", strict_historical_hold=False)
    reasons = list(result["human_reasons"])
    if not is_followup(payload):
        reasons.append("not a follow-up packet")
    return reasons


def approve_packet(
    stem: str,
    payload: dict[str, Any],
    approval_reason: str,
    quality: dict[str, Any],
    model_review: dict[str, Any] | None = None,
) -> None:
    APPROVED.mkdir(parents=True, exist_ok=True)
    clear_safe_historical_hold(payload, quality, source="auto_approve_review_followups")
    refreshed = classify_packet(payload, source_queue="review", strict_historical_hold=False)
    stamp_packet_quality(payload, refreshed)
    payload["status"] = "approved"
    payload["auto_approved_at"] = datetime.now().isoformat(timespec="seconds")
    payload["auto_approval_reason"] = approval_reason
    if model_review:
        payload["model_auto_review"] = model_review
    for key, suffix in {"review_path": ".md", "text_path": ".txt", "html_path": ".html"}.items():
        if key in payload:
            payload[key] = str(APPROVED / f"{stem}{suffix}")

    json_path = REVIEW / f"{stem}.json"
    write_json(json_path, payload)
    for path in queue_paths(stem, REVIEW):
        if path.suffix == ".md":
            content = re.sub(
                r"^status:\s+\w+\s*$",
                "status: approved",
                path.read_text(encoding="utf-8"),
                flags=re.M,
            )
            path.write_text(content, encoding="utf-8")
        path.rename(APPROVED / path.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Strictly auto-approve clean follow-up packets from review.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model-review-limit", type=int, default=3)
    parser.add_argument("--no-model-review", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    approved: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    model_reviewed = 0
    for path in sorted(REVIEW.glob("*.json"), key=lambda item: (item.stat().st_mtime, item.name)):
        payload = load_json(path)
        if not payload or not is_followup(payload):
            continue
        quality = classify_packet(payload, source_queue="review", strict_historical_hold=False)
        reasons = list(quality["human_reasons"])
        model_review: dict[str, Any] | None = None
        approval_reason = "canonical follow-up packet quality pass"
        if (
            quality["decision"] == "repair_candidate"
            and reasons
            and (not quality["historical_hold"] or quality["safe_to_clear_quality_hold"])
            and not args.no_model_review
            and model_reviewed < args.model_review_limit
        ):
            model_reviewed += 1
            model_review = review_packet(payload, reasons, "follow-up")
            if model_review.get("approved"):
                approval_reason = f"model-assisted follow-up packet quality pass: {model_review.get('reason')}"
        item = {
            "stem": path.stem,
            "company_name": payload.get("company_name"),
            "recipient_email": payload.get("recipient_email"),
            "decision": quality["decision"],
            "score": quality["score"],
            "reason_codes": quality["reason_codes"],
            "reasons": reasons,
            "historical_hold_only": quality["historical_hold_only"],
            "model_review": model_review,
        }
        if not is_auto_approval_candidate(quality):
            held.append(item)
            continue
        if len(approved) >= args.limit:
            continue
        approved.append(item)
        if args.write:
            approve_packet(path.stem, payload, approval_reason, quality, model_review)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "write" if args.write else "dry-run",
        "classifier": "packet_quality.classify_packet",
        "limit": args.limit,
        "model_review_enabled": not args.no_model_review,
        "model_reviewed_count": model_reviewed,
        "approved_count": len(approved),
        "held_count": len(held),
        "approved": approved,
        "held_sample": held[:30],
    }
    report_path = REPORT_DIR / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-auto-approve-followups.json"
    latest_path = REPORT_DIR / "latest-auto-approve-followups.json"
    write_json(report_path, report)
    write_json(latest_path, report)
    print(
        json.dumps(
            {
                "report_path": str(report_path),
                "approved_count": len(approved),
                "held_count": len(held),
                "approved_stems": [item["stem"] for item in approved],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
