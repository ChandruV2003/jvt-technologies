#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from packet_quality import (
    classify_packet,
    clear_safe_historical_hold,
    stamp_packet_quality,
)


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
QUEUE_ROOT = ROOT / "outreach" / "queue"
SCHEDULE_ROOT = ROOT / "outreach" / "schedules"

def packet_state(stem: str) -> str:
    for label in ("draft", "review", "approved", "sent", "replied"):
        if (QUEUE_ROOT / label / f"{stem}.json").exists():
            return label
    return "missing"


def packet_paths(label: str, stem: str) -> list[Path]:
    return sorted((QUEUE_ROOT / label).glob(f"{stem}.*"))


def load_packet(label: str, stem: str) -> tuple[dict[str, object], str, str]:
    metadata_path = QUEUE_ROOT / label / f"{stem}.json"
    text_path = QUEUE_ROOT / label / f"{stem}.txt"
    html_path = QUEUE_ROOT / label / f"{stem}.html"
    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    text_body = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
    html_body = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    return metadata, text_body, html_body


def validate_packet(stem: str, label: str) -> list[str]:
    try:
        metadata, _text_body, _html_body = load_packet(label, stem)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"packet_load_failed:{exc}"]
    metadata.setdefault("review_path", str(QUEUE_ROOT / label / f"{stem}.md"))
    metadata.setdefault("text_path", str(QUEUE_ROOT / label / f"{stem}.txt"))
    metadata.setdefault("html_path", str(QUEUE_ROOT / label / f"{stem}.html"))
    quality = classify_packet(
        metadata,
        source_queue=label,
        strict_historical_hold=label == "approved",
    )
    return list(quality["reason_codes"])


def move_packet(stem: str, source: str, target: str, dry_run: bool) -> None:
    if source == target or dry_run:
        return
    target_dir = QUEUE_ROOT / target
    target_dir.mkdir(parents=True, exist_ok=True)
    paths = packet_paths(source, stem)
    if not paths:
        raise FileNotFoundError(f"No packet files for {stem} in {source}")

    for path in paths:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if target == "approved":
                quality = classify_packet(data, source_queue=source, strict_historical_hold=False)
                clear_safe_historical_hold(data, quality, source="auto_review_wave")
                quality = classify_packet(data, source_queue=source, strict_historical_hold=False)
                stamp_packet_quality(data, quality)
            data["status"] = target
            for key, suffix in {
                "review_path": ".md",
                "text_path": ".txt",
                "html_path": ".html",
            }.items():
                if key in data:
                    data[key] = str(target_dir / f"{stem}{suffix}")
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        elif path.suffix == ".md":
            content = path.read_text(encoding="utf-8")
            content = re.sub(r"^status:\s+\w+\s*$", f"status: {target}", content, flags=re.MULTILINE)
            path.write_text(content, encoding="utf-8")

    for path in paths:
        path.rename(target_dir / path.name)


def update_schedule(schedule_path: Path, decisions: list[dict[str, object]], dry_run: bool) -> None:
    if dry_run:
        return
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    by_stem = {str(item["stem"]): item for item in decisions}
    for packet in schedule.get("packets", []):
        stem = str(packet.get("stem") or "")
        decision = by_stem.get(stem)
        if not decision:
            continue
        packet["queue"] = decision["target_state"]
        packet["auto_review"] = {
            "result": decision["result"],
            "issues": decision["issues"],
            "reviewed_at": decision["reviewed_at"],
        }
    schedule["auto_review"] = {
        "reviewed_at": decisions[0]["reviewed_at"] if decisions else datetime.now(timezone.utc).isoformat(),
        "approved": sum(1 for item in decisions if item["result"] == "approved"),
        "held_back": sum(1 for item in decisions if item["result"] == "held_back"),
        "skipped": sum(1 for item in decisions if item["result"] == "skipped"),
        "decisions": decisions,
    }
    schedule_path.write_text(json.dumps(schedule, indent=2) + "\n", encoding="utf-8")


def schedule_stems(schedule: dict[str, object]) -> list[str]:
    stems: list[str] = []
    for packet in schedule.get("packets", []):
        if isinstance(packet, dict) and packet.get("stem"):
            stems.append(str(packet["stem"]))
    for window in schedule.get("send_windows", []):
        if not isinstance(window, dict):
            continue
        for stem in window.get("stems", []):
            if isinstance(stem, str):
                stems.append(stem)
    return list(dict.fromkeys(stems))


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-approve clean outreach packets in a wave and hold back risky packets.")
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--flagged-target", choices=["draft", "review"], default="draft")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    schedule_path = args.schedule
    if not schedule_path.is_absolute():
        schedule_path = SCHEDULE_ROOT / schedule_path
    if not schedule_path.exists():
        raise SystemExit(f"Schedule not found: {schedule_path}")

    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    decisions: list[dict[str, object]] = []
    reviewed_at = datetime.now(timezone.utc).isoformat()

    for stem in schedule_stems(schedule):
        state = packet_state(stem)
        if state not in {"review", "approved"}:
            decisions.append({
                "stem": stem,
                "result": "skipped",
                "source_state": state,
                "target_state": state,
                "issues": [f"state:{state}"],
                "reviewed_at": reviewed_at,
            })
            continue

        issues = validate_packet(stem, state)
        target = "approved" if not issues else args.flagged_target
        if state != target:
            move_packet(stem, state, target, args.dry_run)
        decisions.append({
            "stem": stem,
            "result": "approved" if not issues else "held_back",
            "source_state": state,
            "target_state": target,
            "issues": issues,
            "reviewed_at": reviewed_at,
        })

    update_schedule(schedule_path, decisions, args.dry_run)
    report_path = schedule_path.with_name(f"{schedule_path.stem}-auto-review.json")
    if not args.dry_run:
        report_path.write_text(json.dumps({
            "schedule": str(schedule_path),
            "reviewed_at": reviewed_at,
            "decisions": decisions,
        }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schedule": str(schedule_path),
        "approved": sum(1 for item in decisions if item["result"] == "approved"),
        "held_back": sum(1 for item in decisions if item["result"] == "held_back"),
        "skipped": sum(1 for item in decisions if item["result"] == "skipped"),
        "report": str(report_path),
        "dry_run": args.dry_run,
    }))


if __name__ == "__main__":
    main()
