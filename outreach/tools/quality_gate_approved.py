#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from packet_quality import classify_packet, stamp_packet_quality


ROOT = Path(__file__).resolve().parents[2]
QUEUE_ROOT = ROOT / "outreach" / "queue"
APPROVED = QUEUE_ROOT / "approved"
REVIEW = QUEUE_ROOT / "review"
REPORT_ROOT = ROOT / "outreach" / "quality-reports"


def packet_paths(stem: str, source: Path) -> list[Path]:
    return sorted(source.glob(f"{stem}.*"))


def move_packet(stem: str, reason: str) -> None:
    REVIEW.mkdir(parents=True, exist_ok=True)
    for path in packet_paths(stem, APPROVED):
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            data["status"] = "review"
            data["quality_hold_reason"] = reason
            for key, suffix in {"review_path": ".md", "text_path": ".txt", "html_path": ".html"}.items():
                if key in data:
                    data[key] = str(REVIEW / f"{stem}{suffix}")
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        elif path.suffix == ".md":
            content = re.sub(
                r"^status:\s+\w+\s*$",
                "status: review",
                path.read_text(encoding="utf-8"),
                flags=re.MULTILINE,
            )
            path.write_text(content, encoding="utf-8")
        path.rename(REVIEW / path.name)


def classify(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result = classify_packet(data, source_queue="approved", strict_historical_hold=True)
    if result["decision"] == "approval_candidate":
        stamp_packet_quality(data, result)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "stem": path.stem,
        "decision": "sendable" if result["decision"] == "approval_candidate" else "hold",
        "classification": result["decision"],
        "score": result["score"],
        "reasons": result["human_reasons"],
        "reason_codes": result["reason_codes"],
        "company_name": data.get("company_name"),
        "recipient_email": data.get("recipient_email") or data.get("public_email"),
        "industry": data.get("industry"),
        "practice_area": data.get("practice_area"),
        "contact_page": data.get("contact_page") or data.get("website"),
        "recipient_evidence": result["recipient_evidence"],
        "artifacts": result["artifacts"],
        "generated_at": data.get("generated_at"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the canonical quality gate over approved outreach packets.")
    parser.add_argument("--move-held", action="store_true")
    parser.add_argument("--limit-sendable", type=int, default=0)
    args = parser.parse_args()

    results = [classify(path) for path in sorted(APPROVED.glob("*.json"), key=lambda item: item.stat().st_mtime)]
    sendable = [item for item in results if item["decision"] == "sendable"]
    held = [item for item in results if item["decision"] != "sendable"]
    if args.limit_sendable:
        sendable = sendable[: args.limit_sendable]

    if args.move_held:
        for item in held:
            move_packet(str(item["stem"]), "; ".join(item["reasons"]) or "canonical packet-quality hold")

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "classifier": "packet_quality.classify_packet",
        "approved_count_seen": len(results),
        "sendable_count": len(sendable),
        "held_count": len(held),
        "sendable": sendable,
        "held": held,
        "moved_held_to_review": bool(args.move_held),
    }
    report_path = REPORT_ROOT / f"{datetime.now().date().isoformat()}-approved-quality-gate.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "report_path": str(report_path),
                "approved_count_seen": report["approved_count_seen"],
                "sendable_count": report["sendable_count"],
                "held_count": report["held_count"],
                "moved_held_to_review": report["moved_held_to_review"],
                "sendable_stems": [item["stem"] for item in sendable],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
