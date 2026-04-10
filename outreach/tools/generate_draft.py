#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path


DEFAULT_SENDER = "Chandru Vasu"
DEFAULT_SENDER_TITLE = "Founder, JVT Technologies"
DEFAULT_REPLY_TO = "hello@jvt-technologies.com"
DEFAULT_SITE_URL = "https://jvt-technologies.com"


def load_lead(db_path: Path, lead_id: int) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    if row is None:
        raise SystemExit(f"Lead {lead_id} not found in {db_path}")
    return row


def render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def parse_subject_and_body(template_text: str) -> tuple[str, str]:
    lines = template_text.splitlines()
    if not lines or not lines[0].startswith("Subject:"):
        raise SystemExit("Template must start with a Subject: line")
    subject = lines[0].split(":", 1)[1].strip()
    body = "\n".join(lines[1:]).strip()
    return subject, body


def build_fit_reason(notes: str, practice_area: str, city_state: str, manual_reason: str) -> str:
    note_summary = notes.split("Source:", 1)[0].strip()
    if manual_reason:
        return manual_reason
    if note_summary:
        return note_summary
    if practice_area and city_state:
        return (
            f"Based on the visible {practice_area.lower()} work in {city_state}, "
            "it seemed plausible that a private, citation-based document workflow could be relevant."
        )
    if practice_area:
        return (
            f"Based on the visible {practice_area.lower()} work, it seemed plausible that a private, "
            "citation-based document workflow could be relevant."
        )
    return "It looked like your team may have document-heavy internal workflows where grounded, private search could help."


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "draft"


def discover_html_template(template_path: Path) -> Path | None:
    candidate = template_path.parent / "html" / f"{template_path.stem}.html"
    return candidate if candidate.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reviewed outreach drafts from lead data")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--lead-id", required=True, type=int)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--html-template", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--contact-name", default="there")
    parser.add_argument("--sender-name", default=DEFAULT_SENDER)
    parser.add_argument("--sender-title", default=DEFAULT_SENDER_TITLE)
    parser.add_argument("--sender-company", default="JVT Technologies")
    parser.add_argument("--reply-to-email", default=DEFAULT_REPLY_TO)
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL)
    parser.add_argument("--demo-video-url", default="")
    parser.add_argument("--fit-reason", default="")
    args = parser.parse_args()

    lead = load_lead(args.db, args.lead_id)
    template_text = args.template.read_text(encoding="utf-8")
    subject_template, text_template = parse_subject_and_body(template_text)
    html_template_path = args.html_template or discover_html_template(args.template)

    city_state = lead["city_state"] or ""
    practice_area = lead["practice_area"] or ""
    fit_reason = build_fit_reason(lead["notes"] or "", practice_area, city_state, args.fit_reason)
    values = {
        "company_name": lead["company_name"] or "",
        "website": lead["website"] or "",
        "city_state": city_state,
        "industry": lead["industry"] or "",
        "practice_area": practice_area,
        "contact_page": lead["contact_page"] or "",
        "public_email": lead["public_email"] or "",
        "notes": lead["notes"] or "",
        "fit_score": str(lead["fit_score"] or 0),
        "contact_name": args.contact_name,
        "sender_name": args.sender_name,
        "sender_title": args.sender_title,
        "sender_company": args.sender_company,
        "reply_to_email": args.reply_to_email,
        "fit_reason": fit_reason,
        "site_url": args.site_url,
        "demo_video_url": args.demo_video_url,
        "subject": "",
        "today": date.today().isoformat(),
    }
    subject = render(subject_template, values)
    values["subject"] = subject
    text_body = render(text_template, values)
    html_body = None
    if html_template_path:
        html_body = render(html_template_path.read_text(encoding="utf-8"), values)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(lead["company_name"])
    basename = f"{date.today().isoformat()}-{slug}-{args.template.stem}"
    review_path = args.output_dir / f"{basename}.md"
    text_path = args.output_dir / f"{basename}.txt"
    html_path = args.output_dir / f"{basename}.html"
    metadata_path = args.output_dir / f"{basename}.json"

    review_path.write_text(
        "\n".join(
            [
                f"lead_id: {lead['id']}",
                f"company_name: {lead['company_name']}",
                f"fit_score: {lead['fit_score']}",
                f"subject: {subject}",
                f"reply_to: {args.reply_to_email}",
                "status: draft",
                f"template: {args.template.name}",
                f"generated_at: {datetime.now().isoformat(timespec='seconds')}",
                "",
                text_body,
                "",
            ]
        ),
        encoding="utf-8",
    )
    text_path.write_text(text_body + "\n", encoding="utf-8")
    if html_body is not None:
        html_path.write_text(html_body + "\n", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "lead_id": lead["id"],
                "company_name": lead["company_name"],
                "fit_score": lead["fit_score"],
                "subject": subject,
                "reply_to_email": args.reply_to_email,
                "site_url": args.site_url,
                "demo_video_url": args.demo_video_url,
                "template": args.template.name,
                "html_template": html_template_path.name if html_template_path else None,
                "review_path": str(review_path),
                "text_path": str(text_path),
                "html_path": str(html_path) if html_body is not None else None,
                "status": "draft",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(review_path)


if __name__ == "__main__":
    main()
