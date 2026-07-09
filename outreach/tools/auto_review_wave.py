#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
QUEUE_ROOT = ROOT / "outreach" / "queue"
SCHEDULE_ROOT = ROOT / "outreach" / "schedules"

GENERIC_NAME_MARKERS = {
    "tax preparation",
    "accounting and advisory firm",
    "a premier small business focused cpa firm",
    "parents estate planning law firm",
    "home page",
    "contact us",
    "cpa websites",
    "certified public accounting firm",
}

GENERIC_NAME_PATTERNS = [
    re.compile(r"^[A-Z][A-Za-z .'-]+,\s*[A-Z]{2}\s+Accounting Firm$"),
    re.compile(r"^[A-Z][A-Za-z .'-]+\s+Estate Planning Law Firm$"),
    re.compile(r"^about\s+", re.IGNORECASE),
    re.compile(r"^cpa\s+in\s+[A-Za-z .,'-]+$", re.IGNORECASE),
    re.compile(r"^[A-Za-z .,'-]+\s+cpa\s+firm$", re.IGNORECASE),
    re.compile(r"^trusted\s+accounting\s+firm\s+for\s+business\b", re.IGNORECASE),
    re.compile(r"^accounting\s*&\s*consulting\s+firm\s+in\s+[A-Za-z ,.]+$", re.IGNORECASE),
    re.compile(r"^bookkeeping\s+services\s+in\s+[A-Za-z ,]+", re.IGNORECASE),
    re.compile(r"\b(home|about|contact)\s+[-|]\s+", re.IGNORECASE),
]

POLLUTED_LOCATION_PATTERNS = [
    re.compile(r"\bour expertise\b", re.IGNORECASE),
    re.compile(r"\bprovides small business\b", re.IGNORECASE),
    re.compile(r"\bfrom our offices\b", re.IGNORECASE),
    re.compile(r"\bwe have professional\b", re.IGNORECASE),
    re.compile(r"\bhas served the\b", re.IGNORECASE),
    re.compile(r"\bgreater [A-Z][A-Za-z .'-]+,\s*[A-Z]{2}\b"),
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\{\{.+?\}\}"),
    re.compile(r"\[[A-Z0-9_ -]{3,}\]"),
    re.compile(r"\b(TODO|TBD|INSERT|FILL IN)\b", re.IGNORECASE),
]
TARGET_INDUSTRIES = {
    "Accounting / Tax Firm",
    "Construction / Contracting",
    "Dental / Healthcare Admin",
    "Home Services",
    "IT / Ballot Services",
    "Law Firm",
    "Mortgage / Title Services",
    "Property Management",
}
SOFTWARE_PLATFORM_PATTERNS = [
    re.compile(r"\bsoftware platform\b", re.IGNORECASE),
    re.compile(r"\bpractice management software\b", re.IGNORECASE),
    re.compile(r"\bbusiness management software\b", re.IGNORECASE),
    re.compile(r"\bworkflow software\b", re.IGNORECASE),
    re.compile(r"\bsaas\b", re.IGNORECASE),
    re.compile(r"\bplatform for\b", re.IGNORECASE),
    re.compile(r"\bjetpack workflow\b", re.IGNORECASE),
]


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


def root_domain(value: str) -> str:
    clean = value.lower().removeprefix("www.").split(":", 1)[0]
    parts = [part for part in clean.split(".") if part]
    if len(parts) < 2:
        return clean
    return ".".join(parts[-2:])


def email_matches_website(recipient_email: str, website: str) -> bool:
    if "@" not in recipient_email or not website:
        return True
    parsed = urllib.parse.urlparse(website if "://" in website else f"https://{website}")
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    if not host:
        return True
    email_domain = recipient_email.rsplit("@", 1)[1]
    return root_domain(email_domain) == root_domain(host)


def validate_packet(stem: str, label: str) -> list[str]:
    issues: list[str] = []
    try:
        metadata, text_body, html_body = load_packet(label, stem)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"packet_load_failed:{exc}"]

    company_name = str(metadata.get("company_name") or "").strip()
    recipient_email = str(metadata.get("recipient_email") or "").strip()
    subject = str(metadata.get("subject") or "").strip()
    website = str(metadata.get("contact_page") or metadata.get("website") or "").strip()
    city_state = str(metadata.get("city_state") or "").strip()
    industry = str(metadata.get("industry") or "").strip()
    practice_area = str(metadata.get("practice_area") or "").strip()
    notes = str(metadata.get("notes") or "").strip()
    quality_hold_reason = str(metadata.get("quality_hold_reason") or "").strip()

    if not company_name:
        issues.append("missing_company_name")
    if quality_hold_reason:
        issues.append("existing_quality_hold")
    if company_name.lower() in GENERIC_NAME_MARKERS:
        issues.append("generic_company_name")
    if any(pattern.search(company_name) for pattern in GENERIC_NAME_PATTERNS):
        issues.append("generic_company_name")
    if industry and industry not in TARGET_INDUSTRIES:
        issues.append("off_target_industry")
    target_context = "\n".join([company_name, industry, practice_area, website, notes])
    if any(pattern.search(target_context) for pattern in SOFTWARE_PLATFORM_PATTERNS):
        issues.append("software_platform_target")
    if any(pattern.search(city_state) for pattern in POLLUTED_LOCATION_PATTERNS):
        issues.append("polluted_location_text")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient_email):
        issues.append("invalid_recipient_email")
    elif not email_matches_website(recipient_email, website):
        issues.append("email_domain_mismatch")
    if not subject:
        issues.append("missing_subject")
    if len(subject) > 110:
        issues.append("subject_too_long")
    if len(text_body.strip()) < 350:
        issues.append("short_text_body")
    if not html_body.strip():
        issues.append("missing_html_body")

    combined = "\n".join([subject, text_body, html_body])
    if any(pattern.search(combined) for pattern in PLACEHOLDER_PATTERNS):
        issues.append("unresolved_placeholder")
    if "unsubscribe" in combined.lower():
        issues.append("bulk_unsubscribe_language")

    return issues


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
