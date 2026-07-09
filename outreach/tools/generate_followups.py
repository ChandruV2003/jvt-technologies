#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from email_theme import DEFAULT_REPLY_TO, DEFAULT_SITE_URL, render_text_email_html
from model_copywriter import rewrite_email


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
QUEUE_ROOT = ROOT / "outreach" / "queue"
DEFAULT_TEMPLATE = ROOT / "outreach" / "templates" / "practical-ai-follow-up-1.md"
DEFAULT_DB = ROOT / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
REPORT_DIR = ROOT / "outreach" / "schedules" / "followups"
INTERNAL_RECIPIENTS = {
    "chandruvasu@icloud.com",
    "chandruv@icloud.com",
    "chandru@jvt-technologies.com",
    "chandruv@jvt-technologies.com",
}
SUSPICIOUS_LOCAL_PARTS = {
    "career",
    "careers",
    "employment",
    "hr",
    "jobs",
    "seo",
    "marketing",
    "webmaster",
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "recruiter",
    "recruiting",
    "resumes",
    "talent",
}
RECRUITING_PATH_RE = re.compile(r"/(careers?|employment|jobs?|recruiting|talent)(?:/|$)", re.IGNORECASE)
GENERIC_COMPANY_PATTERNS = (
    re.compile(r"^top\s+", re.IGNORECASE),
    re.compile(r"^cpa\s+firm\b", re.IGNORECASE),
    re.compile(r"\bcpa\s+[a-z ,.-]+accounting\s+firm\b", re.IGNORECASE),
    re.compile(r"^[a-z .'-]+,\s*[A-Z]{2}\s+(accounting|cpa|law|property)\b", re.IGNORECASE),
    re.compile(r"\b(accounting|cpa|law)\s+firm\s+for\b", re.IGNORECASE),
    re.compile(r"\b(home|contact|about|splash)\s+page\b", re.IGNORECASE),
    re.compile(r"\b(best|expert|trusted)\s+(accounting|cpa|law)\b", re.IGNORECASE),
    re.compile(r"\bwebsites?\b", re.IGNORECASE),
    re.compile(r"\boutsourcing\s+services\b", re.IGNORECASE),
    re.compile(r"\s[-|–—]\s*$", re.IGNORECASE),
)
OFF_TARGET_TERMS = (
    "outsourcing",
    "outsourced",
    "seo",
    "web design",
    "software platform",
    "staffing",
)


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "follow-up"


def is_internal_or_test(payload: dict[str, object]) -> bool:
    recipient = str(payload.get("recipient_email") or "").strip().lower()
    company = str(payload.get("company_name") or "").strip().lower()
    if not recipient or recipient in INTERNAL_RECIPIENTS or recipient.endswith("@jvt-technologies.com"):
        return True
    return "jvt technologies" in company or "self-test" in company or "test" == company


def rejection_reasons(payload: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    recipient = str(payload.get("recipient_email") or "").strip().lower()
    company = str(payload.get("company_name") or "").strip()
    contact_page = str(payload.get("contact_page") or payload.get("website") or "").strip()
    company_lower = company.lower()
    if not company or any(pattern.search(company) for pattern in GENERIC_COMPANY_PATTERNS):
        reasons.append("generic or page-title company name")
    if "@" not in recipient:
        reasons.append("missing or invalid recipient")
    else:
        local_part = recipient.split("@", 1)[0]
        if (
            local_part in SUSPICIOUS_LOCAL_PARTS
            or "career" in local_part
            or "recruit" in local_part
            or "resume" in local_part
        ):
            reasons.append("suspicious recipient local part")
    if contact_page:
        parsed = re.sub(r"^[a-z]+://[^/]+", "", contact_page, flags=re.IGNORECASE)
        if RECRUITING_PATH_RE.search(parsed):
            reasons.append("careers/recruiting contact page")
    if any(term in company_lower for term in OFF_TARGET_TERMS):
        reasons.append("off-target company category")
    return reasons


def existing_followup_keys(queue_root: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for queue_name in ("draft", "review", "approved", "sent", "replied"):
        directory = queue_root / queue_name
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            parent = str(payload.get("follow_up_parent_stem") or "")
            stage = str(payload.get("follow_up_stage") or "")
            if parent and stage:
                keys.add((parent, stage))
    return keys


def template_subject_and_body(template_path: Path) -> tuple[str, str]:
    content = template_path.read_text(encoding="utf-8").strip()
    lines = content.splitlines()
    if not lines or not lines[0].lower().startswith("subject:"):
        raise SystemExit(f"Template is missing a Subject line: {template_path}")
    subject = lines[0].split(":", 1)[1].strip()
    body = "\n".join(lines[1:]).strip()
    return subject, body


def fill_template(text: str, values: dict[str, str]) -> str:
    output = text
    for key, value in values.items():
        output = output.replace(f"{{{{{key}}}}}", value)
    return output


def html_from_text(
    text: str,
    *,
    title: str,
    preheader: str,
    site_url: str,
    reply_to_email: str,
) -> str:
    return render_text_email_html(
        text,
        title=title,
        preheader=preheader,
        site_url=site_url,
        reply_to_email=reply_to_email,
    )


def followup_stem(parent_stem: str, company_name: str) -> str:
    if parent_stem.endswith("-initial-introduction"):
        return parent_stem[: -len("-initial-introduction")] + "-follow-up-1"
    return f"{parent_stem}-{slugify(company_name)}-follow-up-1"


def fit_reason(payload: dict[str, object]) -> str:
    for key in ("personalized_offer", "likely_pain", "public_context"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    company = str(payload.get("company_name") or "your team").strip()
    return (
        f"For {company}, I would keep the first version narrow: one workflow, one intake or document packet, "
        "and a human review step before anything goes to a client."
    )


def candidate_packets(queue_root: Path, min_age_days: int, limit: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    sent_dir = queue_root / "sent"
    cutoff = datetime.now() - timedelta(days=min_age_days)
    seen_followups = existing_followup_keys(queue_root)
    candidates: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for path in sorted(sent_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if is_internal_or_test(payload):
            continue
        reasons = rejection_reasons(payload)
        if reasons:
            if len(skipped) < 20:
                skipped.append({
                    "parent_stem": path.stem,
                    "company_name": payload.get("company_name"),
                    "recipient_email": payload.get("recipient_email"),
                    "reasons": reasons,
                })
            continue
        if payload.get("follow_up_stage"):
            continue
        parent_stem = path.stem
        if (parent_stem, "1") in seen_followups:
            continue
        sent_at = parse_timestamp(payload.get("sent_at"))
        if not sent_at or sent_at.replace(tzinfo=None) > cutoff:
            continue
        payload["_source_path"] = str(path)
        payload["_parent_stem"] = parent_stem
        candidates.append(payload)
        if len(candidates) >= limit:
            break
    return candidates, skipped


def write_packet(
    payload: dict[str, object],
    output_dir: Path,
    template_path: Path,
    sender_name: str,
    sender_title: str,
    sender_company: str,
    site_url: str,
    reply_to_email: str,
    use_copywriter: bool,
) -> dict[str, object]:
    subject_template, body_template = template_subject_and_body(template_path)
    parent_stem = str(payload["_parent_stem"])
    company_name = str(payload.get("company_name") or "your team").strip()
    previous_subject = str(payload.get("subject") or "JVT Technologies").strip()
    stem = followup_stem(parent_stem, company_name)
    values = {
        "contact_name": str(payload.get("contact_name") or "there").strip(),
        "company_name": company_name,
        "previous_subject": previous_subject.removeprefix("Re: ").strip(),
        "fit_reason": fit_reason(payload),
        "sender_name": sender_name,
        "sender_title": sender_title,
        "sender_company": sender_company,
        "site_url": site_url,
        "reply_to_email": reply_to_email,
    }
    subject = fill_template(subject_template, values)
    text_body = fill_template(body_template, values)
    copywriter_result: dict[str, object] = {
        "rewritten": False,
        "reason": "copywriter disabled",
    }
    if use_copywriter:
        copywriter_result = rewrite_email(
            {**payload, **values, "recipient_email": payload.get("recipient_email")},
            packet_type="follow-up",
            subject=subject,
            body=text_body,
            site_url=site_url,
        )
        if copywriter_result.get("rewritten"):
            subject = str(copywriter_result.get("subject") or subject).strip()
            text_body = str(copywriter_result.get("body") or text_body).strip() + "\n"
    html_body = html_from_text(
        text_body,
        title=subject,
        preheader=f"A practical JVT follow-up for {company_name}.",
        site_url=site_url,
        reply_to_email=reply_to_email,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {key: value for key, value in payload.items() if not key.startswith("_")}
    metadata.update({
        "status": output_dir.name,
        "subject": subject,
        "template": template_path.name,
        "site_url": site_url,
        "reply_to_email": reply_to_email,
        "follow_up_stage": "1",
        "follow_up_parent_stem": parent_stem,
        "parent_sent_at": payload.get("sent_at"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "copywriter_enabled": use_copywriter,
        "copywriter_result": {
            key: value
            for key, value in copywriter_result.items()
            if key not in {"response", "body", "candidate_body"}
        },
        "copy_voice": "model-copywriter-v1" if copywriter_result.get("rewritten") else "template-fallback",
        "review_path": str(output_dir / f"{stem}.md"),
        "text_path": str(output_dir / f"{stem}.txt"),
        "html_path": str(output_dir / f"{stem}.html"),
    })

    (output_dir / f"{stem}.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (output_dir / f"{stem}.txt").write_text(text_body + "\n", encoding="utf-8")
    (output_dir / f"{stem}.html").write_text(html_body + "\n", encoding="utf-8")
    (output_dir / f"{stem}.md").write_text(
        "\n".join([
            "---",
            f"status: {output_dir.name}",
            "type: follow-up-1",
            f"company_name: {company_name}",
            f"recipient_email: {payload.get('recipient_email')}",
            f"parent_stem: {parent_stem}",
            "---",
            "",
            f"# {subject}",
            "",
            text_body,
            "",
        ]),
        encoding="utf-8",
    )

    return {
        "stem": stem,
        "company_name": company_name,
        "recipient_email": payload.get("recipient_email"),
        "subject": subject,
        "parent_stem": parent_stem,
    }


def update_db_status(db_path: Path, packets: list[dict[str, object]], status: str) -> None:
    lead_ids = [packet.get("lead_id") for packet in packets if isinstance(packet.get("lead_id"), int)]
    if not lead_ids or not db_path.exists():
        return
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "UPDATE leads SET follow_up_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        [(status, lead_id) for lead_id in lead_ids],
    )
    conn.commit()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage first follow-up packets for no-reply sent outreach.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--min-age-days", type=int, default=4)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output-queue", choices=["draft", "review", "approved"], default="review")
    parser.add_argument("--write", action="store_true", help="Write follow-up packets. Without this flag, only reports candidates.")
    parser.add_argument("--sender-name", default="Chandru Vasudevan")
    parser.add_argument("--sender-title", default="Founder")
    parser.add_argument("--sender-company", default="JVT Technologies LLC")
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL)
    parser.add_argument("--reply-to-email", default=DEFAULT_REPLY_TO)
    parser.add_argument("--no-copywriter", action="store_true", help="Disable model copywriter rewrite pass.")
    args = parser.parse_args()

    queue_root = args.root / "outreach" / "queue"
    template_path = args.template if args.template.is_absolute() else args.root / args.template
    db_path = args.db if args.db.is_absolute() else args.root / args.db
    candidates, skipped = candidate_packets(queue_root, args.min_age_days, args.limit)
    written: list[dict[str, object]] = []
    if args.write:
        output_dir = queue_root / args.output_queue
        for payload in candidates:
            written.append(
                write_packet(
                    payload,
                    output_dir,
                    template_path,
                    args.sender_name,
                    args.sender_title,
                    args.sender_company,
                    args.site_url,
                    args.reply_to_email,
                    not args.no_copywriter,
                )
            )
        update_db_status(db_path, candidates, "follow_up_1_staged")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "min_age_days": args.min_age_days,
        "limit": args.limit,
        "write": args.write,
        "output_queue": args.output_queue,
        "copywriter_enabled": not args.no_copywriter,
        "candidate_count": len(candidates),
        "skipped_sample_count": len(skipped),
        "written_count": len(written),
        "skipped_sample": skipped,
        "candidates": [
            {
                "parent_stem": item["_parent_stem"],
                "company_name": item.get("company_name"),
                "recipient_email": item.get("recipient_email"),
                "sent_at": item.get("sent_at"),
                "subject": item.get("subject"),
            }
            for item in candidates
        ],
        "written": written,
    }
    report_path = REPORT_DIR / f"{datetime.now().date().isoformat()}-follow-up-1.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "report_path": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
