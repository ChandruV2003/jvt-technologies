#!/usr/bin/env python3

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from email_theme import render_text_email_html


ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "outreach" / "queue"
APPROVED = QUEUE / "approved"
SENT = QUEUE / "sent"
DB = ROOT / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
SITE_URL = "https://jvt-technologies.com"
REPLY_TO = "hello@jvt-technologies.com"


PACKETS = [
    {
        "lead_id": 345,
        "stem": "2026-05-21-main-street-title-follow-up-1",
        "subject": "Re: A practical document workflow idea for Main Street Title",
        "lane": "AI receptionist / title intake",
        "proof_url": f"{SITE_URL}/ai-receptionist-intake-demo.html",
        "follow_up_stage": "1",
        "parent_stem": "2026-05-21-main-street-title-initial-introduction",
        "body": """Hi there,

Following up with a more concrete angle for Main Street Title.

The smallest useful pilot is not a broad AI system. It is a missed-call and callback intake path for title-status questions, closing-document requests, and after-hours messages.

The assistant would disclose itself, collect the caller's name, property or file context, request type, urgency, and best callback details, then send a clean review packet to a person on your team.

It would not give legal advice, title advice, closing instructions, fee quotes, or anything that should come from a licensed/human reviewer.

Dry-run proof page: https://jvt-technologies.com/ai-receptionist-intake-demo.html

If useful, I can send a one-page pilot scope for that exact intake path.

Best,
Chandru Vasu
Founder, JVT Technologies
JVT Technologies""",
    },
    {
        "lead_id": 344,
        "stem": "2026-05-21-matus-law-group-follow-up-1",
        "subject": "Re: A practical document workflow idea for Matus Law Group",
        "lane": "AI receptionist / law firm intake",
        "proof_url": f"{SITE_URL}/ai-receptionist-intake-demo.html",
        "follow_up_stage": "1",
        "parent_stem": "2026-05-21-matus-law-group-initial-introduction",
        "body": """Hi there,

Following up with a narrower version of the idea for Matus Law Group.

For an estate planning or elder-law office, the useful first pilot is a guarded intake path for missed calls and after-hours messages: caller details, matter type, urgency, family/contact context, and the next human follow-up needed.

The assistant would disclose itself and create a review packet. It would not answer legal questions, interpret documents, promise outcomes, or decide priority without a human reviewer.

Dry-run proof page: https://jvt-technologies.com/ai-receptionist-intake-demo.html

If that would be useful, I can send a one-page pilot scope instead of asking for a meeting first.

Best,
Chandru Vasu
Founder, JVT Technologies
JVT Technologies""",
    },
    {
        "lead_id": 329,
        "stem": "2026-05-19-stone-company-llc-follow-up-1",
        "subject": "Re: A practical document workflow idea for Stone & Company LLC",
        "lane": "Meeting-to-action packets",
        "proof_url": f"{SITE_URL}/meeting-to-action-demo.html",
        "follow_up_stage": "1",
        "parent_stem": "2026-05-19-stone-company-llc-initial-introduction",
        "body": """Hi there,

Following up with a smaller CPA-firm workflow than the original document-assistant note.

One practical starting point is a meeting-to-action packet for recurring client calls: summary, open items, owners, missing documents, deadlines, and a reviewed follow-up draft.

Nothing client-facing goes out automatically. The value is a cleaner packet for the person responsible for the next step.

Dry-run proof page: https://jvt-technologies.com/meeting-to-action-demo.html

Typical starting point is either $75 per packet or a small monthly batch around one recurring meeting type.

If useful, I can send a one-page sample scope.

Best,
Chandru Vasu
Founder, JVT Technologies
JVT Technologies""",
    },
    {
        "lead_id": 305,
        "stem": "2026-06-24-atteign-austin-accounting-advisory-meeting-to-action-follow-up-2",
        "subject": "Re: A practical document workflow idea for Atteign",
        "lane": "Meeting-to-action packets",
        "proof_url": f"{SITE_URL}/meeting-to-action-demo.html",
        "follow_up_stage": "2",
        "parent_stem": "2026-05-15-atteign-austin-accounting-advisory-follow-up-1",
        "body": """Hi there,

One more concrete angle for Atteign, then I will leave this alone.

Instead of a private document assistant, the lower-friction pilot is a meeting-to-action packet for advisory or accounting calls: concise recap, owner list, missing documents, deadlines, and a reviewed follow-up draft.

No CRM integration or autonomous client messaging is needed for the first version. It can start as one recurring call type and one packet format.

Dry-run proof page: https://jvt-technologies.com/meeting-to-action-demo.html

If useful, I can send a one-page sample scope for a small monthly batch.

Best,
Chandru Vasu
Founder, JVT Technologies
JVT Technologies""",
    },
    {
        "lead_id": 310,
        "stem": "2026-06-24-sound-management-property-intake-follow-up-2",
        "subject": "Re: A practical document workflow idea for Sound Management",
        "lane": "AI receptionist / property intake",
        "proof_url": f"{SITE_URL}/ai-receptionist-intake-demo.html",
        "follow_up_stage": "2",
        "parent_stem": "2026-05-15-sound-management-follow-up-1",
        "body": """Hi there,

One more concrete angle for Sound Management, then I will leave this alone.

The smaller pilot is a guarded intake path for missed calls and after-hours property requests: caller details, property address, maintenance or leasing category, urgency, and the handoff needed for a human reviewer.

The assistant would disclose itself and create a review packet. It would not approve repairs, quote pricing, change lease terms, or promise response times.

Dry-run proof page: https://jvt-technologies.com/ai-receptionist-intake-demo.html

If useful, I can send a one-page sample scope for that exact intake path.

Best,
Chandru Vasu
Founder, JVT Technologies
JVT Technologies""",
    },
]


def lead(lead_id: int) -> sqlite3.Row:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    if row is None:
        raise SystemExit(f"Lead {lead_id} missing")
    return row


def existing_metadata(stem: str) -> dict:
    for directory in (APPROVED, SENT, QUEUE / "review", QUEUE / "draft"):
        path = directory / f"{stem}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def parent_sent_at(parent_stem: str) -> str:
    path = SENT / f"{parent_stem}.json"
    if not path.exists():
        return ""
    return str(json.loads(path.read_text(encoding="utf-8")).get("sent_at") or "")


def write_packet(config: dict) -> str:
    row = lead(int(config["lead_id"]))
    stem = config["stem"]
    now = datetime.now().isoformat(timespec="seconds")
    body = config["body"].strip()
    subject = config["subject"]
    metadata = existing_metadata(stem)
    metadata.update(
        {
            "lead_id": row["id"],
            "company_name": row["company_name"],
            "fit_score": row["fit_score"],
            "recipient_email": row["public_email"],
            "contact_page": row["contact_page"],
            "city_state": row["city_state"] or "",
            "industry": row["industry"] or "",
            "practice_area": row["practice_area"] or "",
            "subject": subject,
            "reply_to_email": REPLY_TO,
            "site_url": SITE_URL,
            "template": "priority-proof-backed-followup",
            "html_template": None,
            "status": "approved",
            "generated_at": now,
            "offer_lane": config["lane"],
            "proof_url": config["proof_url"],
            "proof_packet_note": "Proof-backed priority wedge packet generated after public recipient verification.",
            "follow_up_stage": config["follow_up_stage"],
            "follow_up_parent_stem": config["parent_stem"],
            "parent_sent_at": parent_sent_at(config["parent_stem"]),
        }
    )

    APPROVED.mkdir(parents=True, exist_ok=True)
    base = APPROVED / stem
    metadata["review_path"] = str(base.with_suffix(".md"))
    metadata["text_path"] = str(base.with_suffix(".txt"))
    metadata["html_path"] = str(base.with_suffix(".html"))

    base.with_suffix(".txt").write_text(body + "\n", encoding="utf-8")
    base.with_suffix(".html").write_text(
        render_text_email_html(
            body,
            title=subject,
            preheader=f"A concrete JVT proof packet for {row['company_name']}.",
            site_url=SITE_URL,
            reply_to_email=REPLY_TO,
        )
        + "\n",
        encoding="utf-8",
    )
    base.with_suffix(".md").write_text(
        "\n".join(
            [
                "---",
                "status: approved",
                f"type: follow-up-{config['follow_up_stage']}",
                f"company_name: {row['company_name']}",
                f"recipient_email: {row['public_email']}",
                f"offer_lane: {config['lane']}",
                f"proof_url: {config['proof_url']}",
                f"parent_stem: {config['parent_stem']}",
                "---",
                "",
                f"# {subject}",
                "",
                body,
                "",
            ]
        ),
        encoding="utf-8",
    )
    base.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return stem


def main() -> None:
    written = [write_packet(packet) for packet in PACKETS]
    print(json.dumps({"written": written, "count": len(written)}, indent=2))


if __name__ == "__main__":
    main()
