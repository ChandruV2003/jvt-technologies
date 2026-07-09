#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from email_theme import render_text_email_html


DEFAULT_SENDER = "Chandru Vasudevan"
DEFAULT_SENDER_TITLE = "Founder"
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
    if note_summary.lower().startswith("auto-researched"):
        if practice_area and city_state:
            return (
                f"That stood out because {practice_area.lower()} work in {city_state} tends to be "
                "document-heavy, private, and repeatable enough for a narrow AI workflow."
            )
        if practice_area:
            return (
                f"That stood out because {practice_area.lower()} work tends to be document-heavy, "
                "private, and repeatable enough for a narrow AI workflow."
            )
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


def build_lead_context(practice_area: str, city_state: str, industry: str) -> str:
    focus = practice_area or industry
    if focus and city_state:
        return f"teams doing {focus} work in {city_state}"
    if focus:
        return f"teams doing {focus} work"
    if city_state:
        return f"document-heavy professional-service teams in {city_state}"
    return "document-heavy professional-service teams"


def compact_join(parts: list[str]) -> str:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def primary_focus(practice_area: str, industry: str) -> str:
    raw_parts = re.split(r",|/|\band\b", practice_area, flags=re.I)
    parts = [part.strip() for part in raw_parts if part.strip()]
    if parts:
        return parts[0]
    return industry or "professional services"


def build_personalization(industry: str, practice_area: str, city_state: str, notes: str) -> dict[str, str]:
    combined = " ".join([industry, practice_area, notes]).lower()
    focus = primary_focus(practice_area, industry)
    location_phrase = f" in {city_state}" if city_state else ""

    if any(term in combined for term in ["elder", "medicaid", "life care", "long-term", "special needs"]):
        workflow_examples = compact_join(
            [
                "intake notes",
                "Medicaid or benefits checklists",
                "care-planning references",
                "estate-planning templates",
            ]
        )
        likely_pain = (
            "finding the right internal answer quickly when a client question depends on policy details, "
            "planning history, and prior templates"
        )
        personalized_offer = (
            f"For {focus.lower()} work, I would start with a small private search workflow around "
            "intake details, planning checklists, and cited answers from approved internal material."
        )
    elif any(term in combined for term in ["estate", "probate", "trust", "asset protection", "wills"]):
        workflow_examples = compact_join(
            [
                "planning questionnaires",
                "trust and estate templates",
                "probate checklists",
                "client follow-up notes",
            ]
        )
        likely_pain = (
            "keeping repeat planning questions and document templates searchable without relying on memory "
            "or digging through folders"
        )
        personalized_offer = (
            f"For {focus.lower()} work, I would mock up a workflow that finds the right planning template, "
            "surfaces the relevant checklist, and cites the internal source used for the answer."
        )
    elif any(term in combined for term in ["dental", "dentist", "orthodontic", "oral surgery", "new patient", "patient forms"]):
        workflow_examples = compact_join(
            [
                "new-patient calls",
                "appointment requests",
                "insurance questions",
                "after-hours voicemail",
            ]
        )
        likely_pain = (
            "turning missed calls and repeated front-desk questions into clean intake notes that staff can "
            "review before calling patients back"
        )
        personalized_offer = (
            f"For {focus.lower()} work, I would start with a disclosed AI voice intake pilot that captures "
            "the caller's request, urgency, callback details, and missing information without giving medical advice or confirming appointments."
        )
    elif any(term in combined for term in ["hoa election", "condominium election", "ballot", "voting", "inspector of election", "board meeting"]):
        workflow_examples = compact_join(
            [
                "client request packets",
                "meeting checklists",
                "ballot-process milestones",
                "status emails",
            ]
        )
        likely_pain = (
            "keeping election and board-meeting workflows organized without losing deadline, document, or review status"
        )
        personalized_offer = (
            f"For {focus.lower()} work, I would start with a review-first workflow assistant that builds "
            "job packets, tracks missing items, and drafts status updates while leaving election-sensitive decisions with staff."
        )
    elif any(term in combined for term in ["business law", "corporate", "contracts", "general counsel", "commercial"]):
        workflow_examples = compact_join(
            [
                "contract templates",
                "entity and governance documents",
                "client intake notes",
                "outside-counsel reference material",
            ]
        )
        likely_pain = (
            "turning prior work, templates, and internal guidance into faster first-pass answers without "
            "losing attorney review"
        )
        personalized_offer = (
            f"For {focus.lower()} work, I would start with a contract-and-entity document assistant that "
            "finds reusable language, flags the source, and leaves final judgment with the team."
        )
    elif any(term in combined for term in ["employment", "labor", "hr", "handbook", "workplace"]):
        workflow_examples = compact_join(
            [
                "employee handbooks",
                "policy templates",
                "HR compliance checklists",
                "workplace-dispute notes",
            ]
        )
        likely_pain = (
            "keeping policy guidance and prior answers consistent when questions come in across many "
            "employer or employee scenarios"
        )
        personalized_offer = (
            f"For {focus.lower()} work, I would start with a policy-and-compliance assistant that searches "
            "approved internal references and returns cited answers for review."
        )
    elif any(term in combined for term in ["account", "cpa", "tax", "bookkeeping", "payroll", "controller"]):
        workflow_examples = compact_join(
            [
                "tax workpapers",
                "monthly-close procedures",
                "bookkeeping SOPs",
                "client advisory notes",
            ]
        )
        likely_pain = (
            "making recurring client-service answers and internal procedures easier to find during busy cycles"
        )
        personalized_offer = (
            f"For {focus.lower()} work, I would start with a private SOP and client-reference assistant that "
            "answers from approved firm material and links back to the source."
        )
    else:
        workflow_examples = compact_join(
            [
                "intake notes",
                "internal templates",
                "standard operating procedures",
                "reference documents",
            ]
        )
        likely_pain = (
            "helping the team find the right internal answer faster without moving sensitive material into "
            "a public AI tool"
        )
        personalized_offer = (
            f"For a {focus.lower()} team, I would start with a narrow document-search workflow that answers "
            "from approved internal material and cites the source."
        )

    public_context = (
        f"Your public materials point to {focus.lower()} work{location_phrase}, which usually means the team is moving between "
        f"{workflow_examples}."
    )

    return {
        "primary_focus": focus,
        "public_context": public_context,
        "workflow_examples": workflow_examples,
        "likely_pain": likely_pain,
        "personalized_offer": personalized_offer,
    }


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
    parser.add_argument("--sender-company", default="JVT Technologies LLC")
    parser.add_argument("--reply-to-email", default=DEFAULT_REPLY_TO)
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL)
    parser.add_argument("--demo-video-url", default="")
    parser.add_argument("--fit-reason", default="")
    parser.add_argument("--packet-date", default=date.today().isoformat())
    args = parser.parse_args()

    lead = load_lead(args.db, args.lead_id)
    template_text = args.template.read_text(encoding="utf-8")
    subject_template, text_template = parse_subject_and_body(template_text)
    html_template_path = args.html_template or discover_html_template(args.template)

    city_state = lead["city_state"] or ""
    practice_area = lead["practice_area"] or ""
    fit_reason = build_fit_reason(lead["notes"] or "", practice_area, city_state, args.fit_reason)
    personalization = build_personalization(lead["industry"] or "", practice_area, city_state, lead["notes"] or "")
    lead_context = build_lead_context(practice_area, city_state, lead["industry"] or "")
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
        "lead_context": lead_context,
        "contact_name": args.contact_name,
        "sender_name": args.sender_name,
        "sender_title": args.sender_title,
        "sender_company": args.sender_company,
        "reply_to_email": args.reply_to_email,
        "fit_reason": fit_reason,
        **personalization,
        "site_url": args.site_url,
        "demo_video_url": args.demo_video_url,
        "subject": "",
        "today": args.packet_date,
    }
    recipient_email = (lead["public_email"] or "").strip()
    contact_page = (lead["contact_page"] or "").strip()
    subject = render(subject_template, values)
    values["subject"] = subject
    text_body = render(text_template, values)
    html_body = render_text_email_html(
        text_body,
        title=subject,
        preheader=f"A short JVT Technologies note for {lead['company_name'] or 'your team'}.",
        site_url=args.site_url,
        reply_to_email=args.reply_to_email,
    )
    if html_template_path:
        rendered_html = render(html_template_path.read_text(encoding="utf-8"), values)
        if "jvt-body" in rendered_html:
            html_body = rendered_html

    args.output_dir.mkdir(parents=True, exist_ok=True)
    packet_status = args.output_dir.name if args.output_dir.name in {"draft", "review", "approved", "sent", "replied"} else "draft"
    slug = slugify(lead["company_name"])
    basename = f"{args.packet_date}-{slug}-{args.template.stem}"
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
                f"status: {packet_status}",
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
    html_path.write_text(html_body + "\n", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "lead_id": lead["id"],
                "company_name": lead["company_name"],
                "fit_score": lead["fit_score"],
                "recipient_email": recipient_email,
                "contact_page": contact_page,
                "city_state": city_state,
                "industry": lead["industry"] or "",
                "practice_area": practice_area,
                "lead_context": lead_context,
                "subject": subject,
                "reply_to_email": args.reply_to_email,
                "primary_focus": personalization["primary_focus"],
                "public_context": personalization["public_context"],
                "workflow_examples": personalization["workflow_examples"],
                "likely_pain": personalization["likely_pain"],
                "personalized_offer": personalization["personalized_offer"],
                "site_url": args.site_url,
                "demo_video_url": args.demo_video_url,
                "template": args.template.name,
                "html_template": html_template_path.name if html_template_path else None,
                "review_path": str(review_path),
                "text_path": str(text_path),
                "html_path": str(html_path),
                "status": packet_status,
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
