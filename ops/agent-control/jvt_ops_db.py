#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
DATA_ROOT = CONTROL_ROOT / "data"
STATE_ROOT = CONTROL_ROOT / "state"
OPS_DB = DATA_ROOT / "jvt_ops.sqlite3"
LEAD_DB = REPO_ROOT / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
QUEUE_ROOT = REPO_ROOT / "outreach" / "queue"
INBOX_ROOT = REPO_ROOT / "outreach" / "inbox"
SERVICE_PIPELINE = REPO_ROOT / "strategy" / "venture-pipeline.json"
MODEL_ROUTER_STATE = STATE_ROOT / "latest-model-router.json"
CODEX_STATE = STATE_ROOT / "latest-codex-escalation.json"
REPORT_JSON = STATE_ROOT / "latest-jvt-ops-db.json"
REPORT_MD = STATE_ROOT / "latest-jvt-ops-db.md"


SERVICE_CATALOG = [
    ("private-doc-intel", "Private Document Intelligence", "Controlled document retrieval, summarization, and workflow cleanup.", "active"),
    ("ai-voice-intake", "AI Receptionist / Voice Intake", "After-hours intake, callback capture, qualification, and escalation packets.", "pilot"),
    ("meeting-to-action", "Meeting-To-Action Packets", "Convert calls and meetings into reviewed tasks, owners, and follow-up drafts.", "demo"),
    ("inbox-document-triage", "Inbox / Document Triage", "Classify messy inboxes and document-heavy requests into action queues.", "demo"),
    ("managed-ai-ops", "Managed AI Operations", "Ongoing automation monitoring, QA, reports, and workflow iteration.", "pilot"),
    ("workflow-automation", "Workflow Automation", "Custom agentic automations for repeatable internal business processes.", "pilot"),
    ("document-generation", "Document Generation", "Generate drafts, packets, summaries, forms, and client-ready artifacts.", "demo"),
    ("knowledge-assistant", "Internal Knowledge Assistant", "Private searchable assistant over trusted internal material.", "demo"),
    ("paper-trading-research", "Paper-Only Trading Research", "Market-monitoring and paper-only strategy validation.", "research"),
]

POSITIVE_INBOUND_TERMS = (
    "yes",
    "interested",
    "sounds good",
    "tell me more",
    "send more",
    "demo",
    "meeting",
    "call me",
    "schedule",
    "available",
    "ok",
    "okay",
)

SYSTEM_SENDER_TERMS = (
    "no-reply",
    "noreply",
    "donotreply",
    "mailer-daemon",
    "postmaster",
    "notification",
    "newsletter",
    "bankofamerica",
    "google",
    "microsoft",
    "apple",
    "cloudflare",
    "github",
    "stripe",
    "alpaca",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def count_json(path: Path, *, recursive: bool = False) -> int:
    if not path.exists():
        return 0
    iterator = path.rglob("*.json") if recursive else path.glob("*.json")
    return sum(1 for item in iterator if item.is_file())


def connect() -> sqlite3.Connection:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(OPS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS service_catalog (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            website TEXT,
            industry TEXT,
            city_state TEXT,
            source TEXT NOT NULL DEFAULT 'lead-db',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(name, website)
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            email TEXT,
            role TEXT,
            source TEXT NOT NULL DEFAULT 'lead-db',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE(account_id, email)
        );

        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_system TEXT NOT NULL,
            source_id TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            contact_id INTEGER,
            outreach_status TEXT,
            follow_up_status TEXT,
            fit_score INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
            UNIQUE(source_system, source_id)
        );

        CREATE TABLE IF NOT EXISTS lead_service_fit (
            lead_id INTEGER NOT NULL,
            service_slug TEXT NOT NULL,
            fit_reason TEXT,
            confidence TEXT NOT NULL DEFAULT 'seeded',
            updated_at TEXT NOT NULL,
            PRIMARY KEY(lead_id, service_slug),
            FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE,
            FOREIGN KEY(service_slug) REFERENCES service_catalog(slug) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            service_slug TEXT NOT NULL,
            stage TEXT NOT NULL,
            source TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(service_slug) REFERENCES service_catalog(slug) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            contact_id INTEGER,
            channel TEXT NOT NULL,
            direction TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source_path TEXT,
            summary TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE SET NULL,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
            UNIQUE(channel, event_type, source_path)
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_type TEXT NOT NULL,
            status TEXT NOT NULL,
            source_path TEXT,
            summary TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_backend_status (
            backend_name TEXT PRIMARY KEY,
            available INTEGER NOT NULL,
            state TEXT,
            model TEXT,
            checked_at TEXT NOT NULL,
            metadata_json TEXT
        );

        CREATE TABLE IF NOT EXISTS queue_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_at TEXT NOT NULL,
            draft_count INTEGER NOT NULL,
            review_count INTEGER NOT NULL,
            approved_count INTEGER NOT NULL,
            sent_count INTEGER NOT NULL,
            replied_count INTEGER NOT NULL,
            inbox_new_count INTEGER NOT NULL,
            inbox_reviewed_count INTEGER NOT NULL,
            inbox_closed_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            event_note TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def upsert_services(conn: sqlite3.Connection) -> int:
    now = utc_now()
    for slug, name, description, status in SERVICE_CATALOG:
        conn.execute(
            """
            INSERT INTO service_catalog(slug, name, description, status, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
              name=excluded.name,
              description=excluded.description,
              status=excluded.status,
              updated_at=excluded.updated_at
            """,
            (slug, name, description, status, now),
        )
    return len(SERVICE_CATALOG)


def get_or_create_account_values(
    conn: sqlite3.Connection,
    *,
    name: str,
    website: str = "",
    industry: str = "",
    city_state: str = "",
    source: str = "lead-db",
) -> int:
    now = utc_now()
    name = name.strip() or "Unknown Account"
    website = website.strip()
    conn.execute(
        """
        INSERT OR IGNORE INTO accounts(name, website, industry, city_state, source, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (name, website, industry, city_state, source, now, now),
    )
    conn.execute(
        """
        UPDATE accounts
        SET industry=COALESCE(NULLIF(?, ''), industry),
            city_state=COALESCE(NULLIF(?, ''), city_state),
            source=COALESCE(NULLIF(?, ''), source),
            updated_at=?
        WHERE name=? AND website=?
        """,
        (industry or "", city_state or "", source or "", now, name, website),
    )
    account = conn.execute("SELECT id FROM accounts WHERE name=? AND website=?", (name, website)).fetchone()
    return int(account["id"])


def get_or_create_account(conn: sqlite3.Connection, row: sqlite3.Row) -> int:
    return get_or_create_account_values(
        conn,
        name=str(row["company_name"] or "").strip() or "Unknown Account",
        website=str(row["website"] or "").strip(),
        industry=str(row["industry"] or "").strip(),
        city_state=str(row["city_state"] or "").strip(),
        source="lead-db",
    )


def get_or_create_contact(conn: sqlite3.Connection, account_id: int, email: str | None, *, source: str = "lead-db") -> int | None:
    if not email:
        return None
    email = email.strip().lower()
    if not email:
        return None
    now = utc_now()
    conn.execute(
        """
        INSERT OR IGNORE INTO contacts(account_id, email, role, source, created_at, updated_at)
        VALUES(?, ?, 'public/business contact', ?, ?, ?)
        """,
        (account_id, email, source, now, now),
    )
    conn.execute(
        """
        UPDATE contacts
        SET source=COALESCE(NULLIF(?, ''), source),
            updated_at=?
        WHERE account_id=? AND email=?
        """,
        (source, now, account_id, email),
    )
    contact = conn.execute("SELECT id FROM contacts WHERE account_id=? AND email=?", (account_id, email)).fetchone()
    return int(contact["id"]) if contact else None


def service_fit_for(row: sqlite3.Row) -> list[tuple[str, str]]:
    industry = str(row["industry"] or "").lower()
    notes = str(row["notes"] or "").lower()
    text = f"{industry} {notes}"
    fits: list[tuple[str, str]] = [
        ("inbox-document-triage", "Default fit for public outreach leads with inbox/document workflow pain."),
        ("workflow-automation", "Default fit for repeatable admin workflows that can become a narrow paid pilot."),
    ]
    if any(term in text for term in ("law", "legal", "attorney", "firm")):
        fits.extend([
            ("private-doc-intel", "Legal/document-heavy target likely has retrieval and summarization pain."),
            ("document-generation", "Legal/admin teams often need reviewed draft packets and repeatable document generation."),
            ("knowledge-assistant", "Document-heavy teams can benefit from a private internal knowledge assistant."),
        ])
    if any(term in text for term in ("accounting", "tax", "bookkeeping", "cpa")):
        fits.extend([
            ("document-generation", "Accounting/tax workflows often repeat client request packets and status drafts."),
            ("meeting-to-action", "Client calls can be converted into reviewed action and missing-info packets."),
        ])
    if any(term in text for term in ("dental", "medical", "clinic", "healthcare", "appointment")):
        fits.append(("ai-voice-intake", "Appointment and callback-heavy office may benefit from after-hours intake."))
    if any(term in text for term in ("insurance", "coi", "certificate of insurance", "claim")):
        fits.extend([
            ("inbox-document-triage", "Insurance service requests need structured extraction, routing, and human review."),
            ("document-generation", "Insurance teams often need draft responses and packet generation with staff approval."),
        ])
    if any(term in text for term in ("hoa", "property", "association", "board", "ballot", "election", "av", "it consulting")):
        fits.extend([
            ("workflow-automation", "Board, meeting, and ballot support workflows need checklists, packets, and audit trail."),
            ("meeting-to-action", "Board meetings can be converted into reviewed action packets."),
        ])
    if any(term in text for term in ("title", "mortgage", "closing", "real estate")):
        fits.extend([
            ("document-generation", "Closing-heavy teams need reviewed drafts, checklists, and document packets."),
            ("inbox-document-triage", "Closing-heavy teams often need inbox and missing-info triage."),
        ])
    if any(term in text for term in ("construction", "contractor", "project")):
        fits.extend([
            ("workflow-automation", "Project/admin-heavy contractors need repeatable request and status workflows."),
            ("document-generation", "Contractor admin teams often need reviewed draft responses and packets."),
        ])
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for slug, reason in fits:
        if slug not in seen:
            deduped.append((slug, reason))
            seen.add(slug)
    return deduped


def import_leads(conn: sqlite3.Connection) -> dict[str, int]:
    if not LEAD_DB.exists():
        return {"source_leads": 0, "imported": 0}
    source = sqlite3.connect(LEAD_DB)
    source.row_factory = sqlite3.Row
    rows = source.execute("SELECT * FROM leads").fetchall()
    source.close()

    imported = 0
    for row in rows:
        account_id = get_or_create_account(conn, row)
        contact_id = get_or_create_contact(conn, account_id, row["public_email"])
        now = utc_now()
        source_id = str(row["id"])
        conn.execute(
            """
            INSERT INTO leads(source_system, source_id, account_id, contact_id, outreach_status, follow_up_status, fit_score, notes, created_at, updated_at)
            VALUES('lead-db', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_system, source_id) DO UPDATE SET
              account_id=excluded.account_id,
              contact_id=excluded.contact_id,
              outreach_status=excluded.outreach_status,
              follow_up_status=excluded.follow_up_status,
              fit_score=excluded.fit_score,
              notes=excluded.notes,
              updated_at=excluded.updated_at
            """,
            (
                source_id,
                account_id,
                contact_id,
                row["outreach_status"],
                row["follow_up_status"],
                row["fit_score"],
                row["notes"],
                row["created_at"] or now,
                now,
            ),
        )
        lead = conn.execute("SELECT id FROM leads WHERE source_system='lead-db' AND source_id=?", (source_id,)).fetchone()
        if lead:
            for service_slug, reason in service_fit_for(row):
                conn.execute(
                    """
                    INSERT INTO lead_service_fit(lead_id, service_slug, fit_reason, confidence, updated_at)
                    VALUES(?, ?, ?, 'seeded', ?)
                    ON CONFLICT(lead_id, service_slug) DO UPDATE SET
                      fit_reason=excluded.fit_reason,
                      updated_at=excluded.updated_at
                    """,
                    (int(lead["id"]), service_slug, reason, now),
                )
        imported += 1
    return {"source_leads": len(rows), "imported": imported}


def ingest_queue_files(conn: sqlite3.Connection, limit_per_bucket: int = 1000) -> dict[str, int]:
    counts: dict[str, int] = {}
    now = utc_now()
    for bucket in ("draft", "review", "approved", "sent", "replied"):
        files = sorted((QUEUE_ROOT / bucket).glob("*.json")) if (QUEUE_ROOT / bucket).exists() else []
        counts[bucket] = len(files)
        for path in files[-limit_per_bucket:]:
            payload = load_json(path, {})
            recipient = str(payload.get("recipient_email") or payload.get("email") or "").strip()
            company = str(payload.get("company_name") or payload.get("company") or "").strip()
            summary = f"{bucket} packet"
            if company or recipient:
                summary = f"{bucket} packet for {company or recipient}"
            conn.execute(
                """
                INSERT OR IGNORE INTO interactions(channel, direction, event_type, source_path, summary, metadata_json, created_at)
                VALUES('email', 'outbound', ?, ?, ?, ?, ?)
                """,
                (f"queue:{bucket}", str(path), summary[:500], json.dumps({"recipient": recipient, "company": company}), now),
            )
    return counts


def inbox_text(payload: dict[str, Any]) -> str:
    parts = [
        payload.get("subject"),
        payload.get("summary"),
        payload.get("snippet"),
        payload.get("body_text"),
        payload.get("triage_reason"),
        payload.get("sender_domain"),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def sender_domain_from_email(email: str) -> str:
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].lower().strip()


def is_system_sender(email: str) -> bool:
    value = email.lower()
    domain = sender_domain_from_email(value)
    return any(term in value or term in domain for term in SYSTEM_SENDER_TERMS)


def inferred_account_name(payload: dict[str, Any], sender_name: str, sender_email: str) -> str:
    for key in ("company_name", "company", "account_name", "organization"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    if sender_name and "@" not in sender_name:
        return sender_name.strip()
    domain = sender_domain_from_email(sender_email)
    if domain:
        base = domain.split(".")[0].replace("-", " ").replace("_", " ").strip()
        return base.title() if base else sender_email
    return sender_email or "Inbound Prospect"


def infer_service_slug_from_inbox(payload: dict[str, Any]) -> str:
    text = inbox_text(payload)
    if any(term in text for term in ("dental", "dentist", "patient", "appointment", "front desk", "phone", "voice", "call")):
        return "ai-voice-intake"
    if any(term in text for term in ("ballot", "election", "board", "hoa", "association", "property", "av", "meeting")):
        return "workflow-automation"
    if any(term in text for term in ("insurance", "coi", "certificate", "claim", "coverage")):
        return "inbox-document-triage"
    if any(term in text for term in ("document", "packet", "template", "draft", "form")):
        return "document-generation"
    if any(term in text for term in ("knowledge", "search", "internal docs", "wiki")):
        return "knowledge-assistant"
    return "managed-ai-ops"


def is_business_hit(payload: dict[str, Any]) -> bool:
    sender_name, sender_email = parseaddr(str(payload.get("from") or payload.get("sender") or ""))
    sender_email = sender_email.lower().strip()
    if not sender_email or is_system_sender(sender_email):
        return False
    text = inbox_text(payload)
    subject = str(payload.get("subject") or "").lower()
    bucket = str(payload.get("triage_bucket") or "").lower()
    priority = str(payload.get("triage_priority") or "").lower()
    action = str(payload.get("triage_action") or "").lower()
    if bucket == "direct" or priority == "high" or action == "review":
        return True
    if subject.startswith("re:") and any(term in text for term in POSITIVE_INBOUND_TERMS):
        return True
    return any(term in text for term in ("interested", "demo", "meeting", "call me", "schedule a call", "tell me more"))


def upsert_opportunity(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    service_slug: str,
    stage: str,
    source: str,
    notes: str,
) -> bool:
    now = utc_now()
    existing = conn.execute(
        """
        SELECT id FROM opportunities
        WHERE account_id=? AND service_slug=? AND source=?
        """,
        (account_id, service_slug, source),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE opportunities
            SET stage=?,
                notes=COALESCE(NULLIF(?, ''), notes),
                updated_at=?
            WHERE id=?
            """,
            (stage, notes, now, int(existing["id"])),
        )
        return False
    conn.execute(
        """
        INSERT INTO opportunities(account_id, service_slug, stage, source, notes, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, service_slug, stage, source, notes[:1000], now, now),
    )
    return True


def opportunity_stage_from_inbox(payload: dict[str, Any]) -> str:
    response_status = str(payload.get("response_status") or "").strip().lower()
    if response_status in {"sent", "closed", "resolved"}:
        return "reply-sent-awaiting-next"
    return "inbound-hit-needs-review"


def ingest_inbox_files(conn: sqlite3.Connection, limit_per_bucket: int = 1000) -> dict[str, int]:
    counts: dict[str, int] = {}
    now = utc_now()
    opportunities_created = 0
    opportunities_seen = 0
    for bucket in ("new", "reviewed", "closed"):
        root = INBOX_ROOT / bucket
        files = sorted(root.rglob("*.json")) if root.exists() else []
        counts[bucket] = len(files)
        for path in files[-limit_per_bucket:]:
            payload = load_json(path, {})
            subject = str(payload.get("subject") or payload.get("summary") or bucket).strip()
            conn.execute(
                """
                INSERT OR IGNORE INTO interactions(channel, direction, event_type, source_path, summary, metadata_json, created_at)
                VALUES('email', 'inbound', ?, ?, ?, ?, ?)
                """,
                (f"inbox:{bucket}", str(path), subject[:500], json.dumps({"bucket": bucket}), now),
            )
            if bucket != "closed" and is_business_hit(payload):
                sender_name, sender_email = parseaddr(str(payload.get("from") or payload.get("sender") or ""))
                sender_email = sender_email.lower().strip()
                domain = sender_domain_from_email(sender_email)
                account_id = get_or_create_account_values(
                    conn,
                    name=inferred_account_name(payload, sender_name, sender_email),
                    website=f"https://{domain}" if domain else "",
                    industry=str(payload.get("industry") or payload.get("triage_bucket") or "inbound").strip(),
                    city_state=str(payload.get("city_state") or "").strip(),
                    source="inbox",
                )
                contact_id = get_or_create_contact(conn, account_id, sender_email, source="inbox")
                service_slug = infer_service_slug_from_inbox(payload)
                snippet = str(payload.get("snippet") or payload.get("summary") or "").replace("\r", " ").replace("\n", " ").strip()
                notes = f"{subject} :: {snippet}" if snippet else subject
                created = upsert_opportunity(
                    conn,
                    account_id=account_id,
                    service_slug=service_slug,
                    stage=opportunity_stage_from_inbox(payload),
                    source=str(path),
                    notes=notes,
                )
                opportunities_created += 1 if created else 0
                opportunities_seen += 1
                conn.execute(
                    """
                    UPDATE interactions
                    SET account_id=?, contact_id=?
                    WHERE channel='email' AND direction='inbound' AND event_type=? AND source_path=?
                    """,
                    (account_id, contact_id, f"inbox:{bucket}", str(path)),
                )
    counts["opportunities_seen"] = opportunities_seen
    counts["opportunities_created"] = opportunities_created
    return counts


def sync_backend_status(conn: sqlite3.Connection) -> int:
    states = [load_json(MODEL_ROUTER_STATE, {}), load_json(CODEX_STATE, {})]
    now = utc_now()
    written = 0
    router = states[0]
    for name, item in (router.get("backends") or {}).items():
        conn.execute(
            """
            INSERT INTO model_backend_status(backend_name, available, state, model, checked_at, metadata_json)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(backend_name) DO UPDATE SET
              available=excluded.available,
              state=excluded.state,
              model=excluded.model,
              checked_at=excluded.checked_at,
              metadata_json=excluded.metadata_json
            """,
            (name, 1 if item.get("available") else 0, item.get("state"), item.get("model"), now, json.dumps(item)),
        )
        written += 1
    codex = states[1]
    if codex:
        conn.execute(
            """
            INSERT INTO model_backend_status(backend_name, available, state, model, checked_at, metadata_json)
            VALUES('codex-escalation', ?, ?, ?, ?, ?)
            ON CONFLICT(backend_name) DO UPDATE SET
              available=excluded.available,
              state=excluded.state,
              model=excluded.model,
              checked_at=excluded.checked_at,
              metadata_json=excluded.metadata_json
            """,
            (1 if codex.get("ok") else 0, "ready" if codex.get("ok") else "attention", ((codex.get("policy") or {}).get("default_model")), now, json.dumps(codex)),
        )
        written += 1
    return written


def write_queue_snapshot(conn: sqlite3.Connection, queue_counts: dict[str, int], inbox_counts: dict[str, int]) -> None:
    conn.execute(
        """
        INSERT INTO queue_snapshots(snapshot_at, draft_count, review_count, approved_count, sent_count, replied_count, inbox_new_count, inbox_reviewed_count, inbox_closed_count)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now(),
            queue_counts.get("draft", 0),
            queue_counts.get("review", 0),
            queue_counts.get("approved", 0),
            queue_counts.get("sent", 0),
            queue_counts.get("replied", 0),
            inbox_counts.get("new", 0),
            inbox_counts.get("reviewed", 0),
            inbox_counts.get("closed", 0),
        ),
    )


def table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] if row else 0)


def sync() -> dict[str, Any]:
    conn = connect()
    create_schema(conn)
    services = upsert_services(conn)
    lead_result = import_leads(conn)
    queue_counts = ingest_queue_files(conn)
    inbox_counts = ingest_inbox_files(conn)
    backend_count = sync_backend_status(conn)
    write_queue_snapshot(conn, queue_counts, inbox_counts)
    conn.execute(
        "INSERT INTO audit_log(event_type, event_note, metadata_json, created_at) VALUES('ops-db-sync', 'Synchronized JVT ops database.', ?, ?)",
        (json.dumps({"lead_result": lead_result, "queue_counts": queue_counts, "inbox_counts": inbox_counts}), utc_now()),
    )
    conn.commit()
    report = {
        "generated_at": utc_now(),
        "ok": True,
        "db_path": str(OPS_DB),
        "services_seeded": services,
        "lead_sync": lead_result,
        "queue_counts": queue_counts,
        "inbox_counts": inbox_counts,
        "model_backends_written": backend_count,
        "table_counts": {
            name: table_count(conn, name)
            for name in (
                "service_catalog",
                "accounts",
                "contacts",
                "leads",
                "lead_service_fit",
                "opportunities",
                "interactions",
                "model_backend_status",
                "queue_snapshots",
                "audit_log",
            )
        },
    }
    conn.close()
    write_json(REPORT_JSON, report)
    write_markdown(report)
    return report


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Ops Database",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- DB: `{report['db_path']}`",
        f"- Services seeded: `{report['services_seeded']}`",
        f"- Leads imported: `{report['lead_sync'].get('imported')}`",
        f"- Model backends written: `{report['model_backends_written']}`",
        "",
        "## Queue Counts",
        "",
    ]
    for key, value in sorted((report.get("queue_counts") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Inbox Counts", ""])
    for key, value in sorted((report.get("inbox_counts") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Table Counts", ""])
    for key, value in sorted((report.get("table_counts") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and sync the JVT company ops database.")
    parser.add_argument("command", nargs="?", choices=["sync", "status"], default="sync")
    args = parser.parse_args()
    if args.command == "sync":
        print(json.dumps(sync(), indent=2))
        return
    if REPORT_JSON.exists():
        print(REPORT_JSON.read_text(encoding="utf-8"))
        return
    print(json.dumps({"ok": False, "reason": "ops database has not been synced yet", "db_path": str(OPS_DB)}, indent=2))


if __name__ == "__main__":
    main()
