#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from model_packet_reviewer import review_packet


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
QUEUE_ROOT = ROOT / "outreach" / "queue"
REVIEW = QUEUE_ROOT / "review"
APPROVED = QUEUE_ROOT / "approved"
REPORT_DIR = ROOT / "outreach" / "schedules" / "initial-auto-review"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BLOCKED_LOCAL_PARTS = {
    "career",
    "careers",
    "employment",
    "hr",
    "jobs",
    "marketing",
    "noreply",
    "no-reply",
    "recruit",
    "recruiter",
    "recruiting",
    "resumes",
    "seo",
    "talent",
    "webmaster",
}
GENERIC_NAME_PATTERNS = [
    re.compile(r"^top\s+", re.I),
    re.compile(r"\b(home|contact|about|splash)\s+page\b", re.I),
    re.compile(r"\bcpa\s+firm\s+in\b", re.I),
    re.compile(r"\b(accounting|cpa|law)\s+firm\s+for\b", re.I),
    re.compile(r"\bwebsites?\b", re.I),
    re.compile(r"\boutsourc", re.I),
    re.compile(r"\b(bookkeeping|payroll|tax)\s+services\s+firm\b", re.I),
    re.compile(r"\s[-|–—]\s*$", re.I),
]
TARGET_INDUSTRIES = {
    "Accounting / Tax Firm",
    "Dental / Healthcare Admin",
    "Home Services",
    "IT / Ballot Services",
    "Law Firm",
    "Property Management",
    "Mortgage / Title Services",
    "Construction / Contracting",
}
SOFTWARE_PLATFORM_PATTERNS = [
    re.compile(r"\bsoftware platform\b", re.I),
    re.compile(r"\bpractice management software\b", re.I),
    re.compile(r"\bbusiness management software\b", re.I),
    re.compile(r"\bworkflow software\b", re.I),
    re.compile(r"\bsaas\b", re.I),
    re.compile(r"\bplatform for\b", re.I),
    re.compile(r"^jetpack workflow$", re.I),
]
RECRUITING_PATH_RE = re.compile(r"/(careers?|employment|jobs?|recruiting|talent)(?:/|$)", re.I)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def root_domain(value: str) -> str:
    value = value.lower().strip().removeprefix("www.")
    parts = [part for part in value.split(".") if part]
    if len(parts) < 2:
        return value
    return ".".join(parts[-2:])


def host_from_url(value: str) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc or parsed.path.split("/", 1)[0]


def queue_paths(stem: str, queue: Path) -> list[Path]:
    return sorted(queue.glob(f"{stem}.*"))


def is_followup(payload: dict[str, Any]) -> bool:
    return bool(payload.get("follow_up_stage") or payload.get("follow_up_parent_stem"))


def rejection_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if payload.get("quality_hold_reason"):
        reasons.append(f"existing quality hold: {payload.get('quality_hold_reason')}")
    if is_followup(payload):
        reasons.append("not an initial packet")

    company = str(payload.get("company_name") or "").strip()
    lower_company = company.lower()
    email = str(payload.get("recipient_email") or payload.get("public_email") or "").strip().lower()
    contact_page = str(payload.get("contact_page") or payload.get("website") or "").strip()
    industry = str(payload.get("industry") or "").strip()
    practice_area = str(payload.get("practice_area") or "").strip()
    notes = str(payload.get("notes") or "").strip()

    if not company:
        reasons.append("missing company name")
    if len(company.split()) > 8:
        reasons.append("company name too long to trust automatically")
    if any(pattern.search(company) for pattern in GENERIC_NAME_PATTERNS):
        reasons.append("generic/page-title company name")
    if "jvt technologies" in lower_company or lower_company == "test":
        reasons.append("internal/test company")
    if industry and industry not in TARGET_INDUSTRIES:
        reasons.append(f"off-target industry: {industry}")
    target_context = "\n".join([company, industry, practice_area, contact_page, notes])
    if any(pattern.search(target_context) for pattern in SOFTWARE_PLATFORM_PATTERNS):
        reasons.append("software/SaaS platform target, not a service buyer")

    if not EMAIL_RE.match(email):
        reasons.append("invalid recipient email")
    else:
        local, domain = email.rsplit("@", 1)
        if local in BLOCKED_LOCAL_PARTS or any(token in local for token in ("career", "recruit", "resume")):
            reasons.append("blocked recipient local part")
        if email.endswith("@jvt-technologies.com"):
            reasons.append("internal recipient")
        host = host_from_url(contact_page)
        if host and root_domain(host) != root_domain(domain):
            reasons.append("email domain does not match contact page domain")

    if contact_page:
        parsed = urllib.parse.urlparse(contact_page if "://" in contact_page else f"https://{contact_page}")
        if RECRUITING_PATH_RE.search(parsed.path or ""):
            reasons.append("careers/recruiting contact page")

    if not str(payload.get("subject") or "").strip():
        reasons.append("missing subject")
    if not payload.get("html_path") and not payload.get("text_path"):
        reasons.append("missing rendered message artifact")

    return reasons


def has_existing_quality_hold(payload: dict[str, Any]) -> bool:
    return bool(str(payload.get("quality_hold_reason") or "").strip())


def approve_packet(stem: str, payload: dict[str, Any], approval_reason: str, model_review: dict[str, Any] | None = None) -> None:
    APPROVED.mkdir(parents=True, exist_ok=True)
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
            content = re.sub(r"^status:\s+\w+\s*$", "status: approved", path.read_text(encoding="utf-8"), flags=re.M)
            path.write_text(content, encoding="utf-8")
        path.rename(APPROVED / path.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Strictly auto-approve clean initial packets from review.")
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
        if not payload or is_followup(payload):
            continue
        reasons = rejection_reasons(payload)
        model_review: dict[str, Any] | None = None
        approval_reason = "strict initial packet quality pass"
        if has_existing_quality_hold(payload):
            model_review = {
                "available": False,
                "approved": False,
                "confidence": 0,
                "reason": "existing quality hold is a deterministic veto",
            }
        elif reasons and not args.no_model_review and model_reviewed < args.model_review_limit:
            model_reviewed += 1
            model_review = review_packet(payload, reasons, "initial")
            if model_review.get("approved"):
                reasons = []
                approval_reason = f"model-assisted initial packet quality pass: {model_review.get('reason')}"
        item = {
            "stem": path.stem,
            "company_name": payload.get("company_name"),
            "recipient_email": payload.get("recipient_email"),
            "industry": payload.get("industry"),
            "reasons": reasons,
            "model_review": model_review,
        }
        if reasons:
            held.append(item)
            continue
        if len(approved) >= args.limit:
            continue
        approved.append(item)
        if args.write:
            approve_packet(path.stem, payload, approval_reason, model_review)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "write" if args.write else "dry-run",
        "limit": args.limit,
        "model_review_enabled": not args.no_model_review,
        "model_reviewed_count": model_reviewed,
        "approved_count": len(approved),
        "held_count": len(held),
        "approved": approved,
        "held_sample": held[:40],
    }
    report_path = REPORT_DIR / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-auto-approve-initials.json"
    latest_path = REPORT_DIR / "latest-auto-approve-initials.json"
    write_json(report_path, report)
    write_json(latest_path, report)
    print(json.dumps({
        "report_path": str(report_path),
        "approved_count": len(approved),
        "held_count": len(held),
        "approved_stems": [item["stem"] for item in approved],
    }, indent=2))


if __name__ == "__main__":
    main()
