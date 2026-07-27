#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import formataddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
DATA_ROOT = Path(os.environ.get("JVT_PUBLIC_CONVERSION_DATA_ROOT", CONTROL_ROOT / "data" / "public-conversion-intake"))
SUBMISSION_ROOT = DATA_ROOT / "submissions"
EVENT_ROOT = DATA_ROOT / "events"
DEDUP_INDEX = DATA_ROOT / "dedupe-index.json"
EVENT_LOG = DATA_ROOT / "events.jsonl"
STATE_ROOT = Path(os.environ.get("JVT_PUBLIC_CONVERSION_STATE_ROOT", CONTROL_ROOT / "state"))
REPORT_JSON = STATE_ROOT / "latest-public-conversion-intake.json"
REPORT_MD = STATE_ROOT / "latest-public-conversion-intake.md"
OPS_DB = Path(os.environ.get("JVT_PUBLIC_CONVERSION_OPS_DB", CONTROL_ROOT / "data" / "jvt_ops.sqlite3"))
INBOX_HANDOFF_ROOT = Path(
    os.environ.get("JVT_PUBLIC_CONVERSION_INBOX_ROOT", REPO_ROOT / "outreach" / "inbox" / "new" / "public-intake")
)
MAILBOX_AGENT_ROOT = REPO_ROOT / "outreach" / "mailbox-agent"
if str(MAILBOX_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MAILBOX_AGENT_ROOT))
if str(CONTROL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_ROOT))

from inbox_policy import is_internal_sender, is_system_sender, qualified_external_inbound

import jvt_ops_db


SERVICE_LABELS = {
    "ai-voice-intake": "AI receptionist / intake",
    "meeting-to-action": "Meeting-to-action packets",
    "inbox-document-triage": "Inbox / document triage",
    "workflow-automation": "Workflow cleanup / automation",
    "private-doc-intel": "Private document assistant",
    "document-generation": "Document generation",
    "managed-ai-ops": "Managed AI operations",
}

SERVICE_ALIASES = {
    **{slug: slug for slug in SERVICE_LABELS},
    "ai receptionist": "ai-voice-intake",
    "voice intake": "ai-voice-intake",
    "intake": "ai-voice-intake",
    "meeting": "meeting-to-action",
    "meeting notes": "meeting-to-action",
    "meeting-to-action packets": "meeting-to-action",
    "inbox": "inbox-document-triage",
    "document triage": "inbox-document-triage",
    "inbox triage": "inbox-document-triage",
    "workflow": "workflow-automation",
    "workflow cleanup": "workflow-automation",
    "automation": "workflow-automation",
    "document assistant": "private-doc-intel",
    "private document assistant": "private-doc-intel",
    "knowledge assistant": "private-doc-intel",
    "document generation": "document-generation",
    "managed ai ops": "managed-ai-ops",
    "not sure": "managed-ai-ops",
}

PREFERRED_NEXT_STEPS = {
    "",
    "email",
    "call",
    "demo",
    "scope",
    "not-sure",
}

EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-']+@[A-Z0-9.\-]+\.[A-Z]{2,63}$", re.IGNORECASE)
SUBMISSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{10,79}$")
PLACEHOLDER_RE = re.compile(
    r"^(?:test|example|sample|placeholder|todo|tbd|n/a|na|none|unknown|your name|your company|company|"
    r"first last|john doe|jane doe|asdf|qwerty)$",
    re.IGNORECASE,
)
PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "test.org",
    "invalid",
    "localhost",
}
FREE_MAIL_DOMAINS = {
    "aol.com",
    "gmail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "mail.com",
    "me.com",
    "msn.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}
BLOCKED_LOCAL_PARTS = {
    "admin",
    "career",
    "careers",
    "employment",
    "example",
    "hr",
    "jobs",
    "marketing",
    "no-reply",
    "noreply",
    "recruiting",
    "resumes",
    "seo",
    "support",
    "talent",
    "test",
    "user",
    "webmaster",
}
ATTACHMENT_KEYS = {
    "attachment",
    "attachments",
    "document",
    "documents",
    "file",
    "files",
    "upload",
    "uploads",
    "resume",
}
SENSITIVE_KEYWORD_PATTERNS = (
    re.compile(r"\b(password|passcode|secret|api[_ -]?key|token|credential)s?\b", re.IGNORECASE),
    re.compile(r"\b(ssn|social security|taxpayer id|ein)\b", re.IGNORECASE),
    re.compile(r"\b(credit card|card number|cvv|routing number|bank account|payment data)\b", re.IGNORECASE),
)
SSN_VALUE_RE = re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}(?!\d)")
LABELED_SENSITIVE_NUMBER_RE = re.compile(
    r"\b(?:ssn|social security(?: number)?|routing number|bank account(?: number)?|account number)"
    r"\s*(?:is|:|#)?\s*\d[\d -]{5,20}\d\b",
    re.IGNORECASE,
)
CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
INTAKE_THREAD_LOCK = threading.RLock()


class IntakeError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


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
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with INTAKE_THREAD_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


@contextmanager
def intake_write_lock():
    """Serialize local intake mutations across server threads and processes."""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with INTAKE_THREAD_LOCK:
        with (DATA_ROOT / ".intake.lock").open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def normalize_space(value: Any, *, limit: int = 1000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def is_placeholder(value: str) -> bool:
    return not value or bool(PLACEHOLDER_RE.fullmatch(value.strip()))


def service_slug(value: Any) -> str:
    raw = normalize_space(value, limit=120).lower()
    return SERVICE_ALIASES.get(raw, "")


def clean_submission_id(value: Any) -> str:
    raw = normalize_space(value, limit=100)
    if SUBMISSION_ID_RE.fullmatch(raw):
        return raw
    return ""


def normalize_url(value: Any, *, drop_query: bool = False) -> str:
    raw = normalize_space(value, limit=500)
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if drop_query:
        parsed = parsed._replace(query="", fragment="")
    return urlunparse(parsed)


def source_attribution(payload: dict[str, Any]) -> dict[str, str]:
    nested = payload.get("attribution") if isinstance(payload.get("attribution"), dict) else {}
    raw_source_url = normalize_url(payload.get("source_url") or payload.get("page_url") or nested.get("source_url"))
    parsed = urlparse(raw_source_url) if raw_source_url else None
    params = parse_qs(parsed.query) if parsed else {}

    def first_param(name: str) -> str:
        explicit = normalize_space(payload.get(name) or nested.get(name), limit=160)
        if explicit:
            return explicit
        values = params.get(name)
        return normalize_space(values[0], limit=160) if values else ""

    return {
        "source": normalize_space(payload.get("source") or nested.get("source") or "public-site-workflow-intake", limit=80),
        "source_url": normalize_url(raw_source_url, drop_query=True),
        "page_path": normalize_space(payload.get("page_path") or nested.get("page_path") or (parsed.path if parsed else ""), limit=240),
        "referrer": normalize_url(payload.get("referrer") or nested.get("referrer"), drop_query=True),
        "utm_source": first_param("utm_source"),
        "utm_medium": first_param("utm_medium"),
        "utm_campaign": first_param("utm_campaign"),
        "utm_term": first_param("utm_term"),
        "utm_content": first_param("utm_content"),
    }


def validate_public_business_email(email: str) -> None:
    if not EMAIL_RE.fullmatch(email):
        raise IntakeError("invalid_email", "Use a valid public business email address.")
    local, domain = email.rsplit("@", 1)
    domain = domain.strip(".")
    if is_internal_sender(email):
        raise IntakeError("internal_email", "Use a non-JVT public business email address.")
    if domain in PLACEHOLDER_EMAIL_DOMAINS or domain.endswith(".invalid"):
        raise IntakeError("placeholder_email", "Use a real public business email address.")
    if is_system_sender(email) or local in BLOCKED_LOCAL_PARTS or local.startswith(("no-reply", "noreply")):
        raise IntakeError("blocked_email", "Use a person or shared public business inbox, not a system address.")
    if domain in FREE_MAIL_DOMAINS:
        raise IntakeError("personal_email", "Use a public business email address for the company.")


def is_luhn_valid(value: str) -> bool:
    digits = [int(character) for character in value if character.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def contains_sensitive_value(text: str) -> bool:
    if SSN_VALUE_RE.search(text) or LABELED_SENSITIVE_NUMBER_RE.search(text):
        return True
    return any(is_luhn_valid(match.group(0)) for match in CARD_CANDIDATE_RE.finditer(text))


def reject_attachment_or_sensitive_payload(payload: dict[str, Any]) -> None:
    lowered_keys = {str(key).strip().lower() for key in payload}
    if lowered_keys & ATTACHMENT_KEYS:
        raise IntakeError("attachments_not_allowed", "Do not upload or attach files through this form.")
    text = " ".join(
        normalize_space(payload.get(key), limit=1400)
        for key in ("name", "company", "problem_description", "preferred_next_step", "notes")
    )
    for pattern in SENSITIVE_KEYWORD_PATTERNS:
        if pattern.search(text):
            raise IntakeError(
                "sensitive_details_not_allowed",
                "Describe the workflow without credentials, payment data, health details, or attachments.",
            )
    if contains_sensitive_value(text):
        raise IntakeError(
            "sensitive_details_not_allowed",
            "Describe the workflow without credentials, payment data, health details, or attachments.",
        )


def validate_submission_payload(payload: dict[str, Any]) -> dict[str, Any]:
    reject_attachment_or_sensitive_payload(payload)
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else {}
    submission_id = clean_submission_id(payload.get("submission_id"))
    name = normalize_space(payload.get("name") or contact.get("name"), limit=100)
    email = normalize_email(payload.get("public_business_email") or payload.get("email") or contact.get("email"))
    company = normalize_space(payload.get("company") or contact.get("company"), limit=140)
    slug = service_slug(payload.get("workflow_type") or payload.get("service_interest") or payload.get("service_slug"))
    problem = normalize_space(payload.get("problem_description"), limit=1400)
    next_step = normalize_space(payload.get("preferred_next_step"), limit=80).lower()

    if not submission_id:
        raise IntakeError("invalid_submission_id", "Refresh the page and try again.")
    if is_placeholder(name) or len(name) < 2:
        raise IntakeError("invalid_name", "Use your real name.")
    if is_placeholder(company) or len(company) < 2:
        raise IntakeError("invalid_company", "Use the company name.")
    validate_public_business_email(email)
    if not slug:
        raise IntakeError("invalid_service_interest", "Choose the workflow type that is closest to the problem.")
    if len(problem) < 35 or is_placeholder(problem):
        raise IntakeError("short_problem_description", "Describe the workflow problem in one or two short sentences.")
    if next_step not in PREFERRED_NEXT_STEPS:
        next_step = ""

    normalized_problem = problem.lower()
    dedupe_source = "|".join([email, company.lower(), slug, re.sub(r"\s+", " ", normalized_problem)])
    dedupe_hash = hashlib.sha256(dedupe_source.encode("utf-8")).hexdigest()
    return {
        "submission_id": submission_id,
        "name": name,
        "public_business_email": email,
        "company": company,
        "service_slug": slug,
        "service_interest": SERVICE_LABELS[slug],
        "problem_description": problem,
        "preferred_next_step": next_step,
        "dedupe_key": dedupe_hash,
        "attribution": source_attribution(payload),
    }


def submission_path(record: dict[str, Any]) -> Path:
    created_at = str(record.get("created_at") or utc_now())
    day = created_at[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", created_at[:10]) else "undated"
    return SUBMISSION_ROOT / day / f"{record['submission_id']}.json"


def existing_submission(submission_id: str) -> dict[str, Any]:
    matches = sorted(SUBMISSION_ROOT.glob(f"**/{submission_id}.json"))
    if not matches:
        return {}
    payload = load_json(matches[-1], {})
    return payload if isinstance(payload, dict) else {}


def load_dedupe_index() -> dict[str, str]:
    payload = load_json(DEDUP_INDEX, {})
    return {str(key): str(value) for key, value in payload.items()} if isinstance(payload, dict) else {}


def write_dedupe_index(index: dict[str, str]) -> None:
    write_json(DEDUP_INDEX, dict(sorted(index.items())))


def minimal_submission_record(record: dict[str, Any]) -> dict[str, Any]:
    """Discard raw form PII after the canonical operational handoff is written."""
    contact = record.get("contact") if isinstance(record.get("contact"), dict) else {}
    email = normalize_email(contact.get("email"))
    attribution = record.get("attribution") if isinstance(record.get("attribution"), dict) else {}
    minimal = dict(record)
    minimal["contact"] = {
        "company": normalize_space(contact.get("company"), limit=140),
        "email_domain": email.rsplit("@", 1)[-1] if "@" in email else "",
    }
    problem = str(record.get("problem_description") or "")
    minimal.pop("problem_description", None)
    minimal["problem_digest"] = hashlib.sha256(problem.encode("utf-8")).hexdigest() if problem else ""
    minimal["problem_character_count"] = len(problem)
    minimal["attribution"] = {
        key: normalize_space(attribution.get(key), limit=240)
        for key in (
            "source",
            "source_url",
            "page_path",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
        )
        if attribution.get(key)
    }
    minimal["pii_retention"] = {
        "raw_form_pii": "discarded_after_canonical_handoff",
        "canonical_contact_store": "ops-db-and-inbox-handoff",
    }
    return minimal


def make_inbox_handoff_payload(record: dict[str, Any]) -> dict[str, Any]:
    contact = record["contact"]
    attribution = record.get("attribution") or {}
    subject = f"Public workflow intake: {record['service_interest']}"
    return {
        "status": "new",
        "source": "public-site-workflow-intake",
        "from": formataddr((contact["name"], contact["email"])),
        "to": "JVT Technologies <hello@jvt-technologies.com>",
        "sender_email": contact["email"],
        "recipient_email": "hello@jvt-technologies.com",
        "sender_domain": contact["email"].rsplit("@", 1)[-1],
        "subject": subject,
        "snippet": record["problem_description"][:500],
        "body_preview": record["problem_description"][:1000],
        "captured_at": record["created_at"],
        "message_id": f"public-conversion:{record['submission_id']}",
        "triage_bucket": "direct",
        "triage_priority": "high",
        "triage_action": "review",
        "agent_triage_status": "public_intake_qualified",
        "company_name": contact["company"],
        "service_slug": record["service_slug"],
        "service_interest": record["service_interest"],
        "workflow_type": record["service_slug"],
        "preferred_next_step": record.get("preferred_next_step") or "",
        "public_conversion_submission_id": record["submission_id"],
        "attribution": attribution,
        "guardrail": "Internal intake handoff only. No email send or external commitment has been made.",
    }


def write_inbox_handoff(record: dict[str, Any]) -> Path:
    day = str(record.get("created_at") or utc_now())[:10]
    path = INBOX_HANDOFF_ROOT / day / f"{record['submission_id']}.json"
    write_json(path, make_inbox_handoff_payload(record))
    return path


def sync_record_to_ops_db(record: dict[str, Any], *, db_path: Path | None = None) -> dict[str, Any]:
    db_path = db_path or OPS_DB
    inbox_path = write_inbox_handoff(record)
    payload = load_json(inbox_path, {})
    if not qualified_external_inbound(payload):
        return {
            "qualified": False,
            "reason": "inbox_policy_rejected",
            "inbox_handoff_path": str(inbox_path),
        }

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    jvt_ops_db.create_schema(conn)
    jvt_ops_db.upsert_services(conn)
    email = normalize_email(record["contact"]["email"])
    existing_contact = conn.execute(
        """
        SELECT contacts.id AS contact_id, contacts.account_id
        FROM contacts
        JOIN accounts ON accounts.id = contacts.account_id
        WHERE lower(contacts.email)=?
        ORDER BY CASE WHEN accounts.source='public-intake' THEN 1 ELSE 0 END, contacts.id
        LIMIT 1
        """,
        (email,),
    ).fetchone()
    if existing_contact:
        account_id = int(existing_contact["account_id"])
        contact_id = jvt_ops_db.get_or_create_contact(conn, account_id, email, source="public-intake")
    else:
        account_id = jvt_ops_db.get_or_create_account_values(
            conn,
            name=record["contact"]["company"],
            website="",
            industry="public workflow intake",
            city_state="",
            source="public-intake",
        )
        contact_id = jvt_ops_db.get_or_create_contact(
            conn,
            account_id,
            email,
            source="public-intake",
        )
    service = jvt_ops_db.infer_service_slug_from_inbox(payload)
    notes = f"{record['service_interest']} :: {record['problem_description']}"
    jvt_ops_db.upsert_opportunity(
        conn,
        account_id=account_id,
        service_slug=service,
        stage="inbound-hit-needs-review",
        source=str(inbox_path),
        notes=notes[:1000],
    )
    opportunity = conn.execute(
        "SELECT id FROM opportunities WHERE source=? ORDER BY id LIMIT 1",
        (str(inbox_path),),
    ).fetchone()
    conn.execute(
        """
        INSERT OR IGNORE INTO interactions(account_id, contact_id, channel, direction, event_type, source_path, summary, metadata_json, created_at)
        VALUES(?, ?, 'site', 'inbound', 'public-workflow-intake', ?, ?, ?, ?)
        """,
        (
            account_id,
            contact_id,
            str(inbox_path),
            f"Public workflow intake from {record['contact']['company']}"[:500],
            json.dumps({
                "submission_id": record["submission_id"],
                "service_slug": service,
                "preferred_next_step": record.get("preferred_next_step") or "",
                "attribution": record.get("attribution") or {},
                "no_send": True,
            }),
            record["created_at"],
        ),
    )
    conn.commit()
    conn.close()
    return {
        "qualified": True,
        "account_id": account_id,
        "contact_id": contact_id,
        "opportunity_id": int(opportunity["id"]) if opportunity else None,
        "service_slug": service,
        "inbox_handoff_path": str(inbox_path),
    }


def record_client_event(payload: dict[str, Any], event_type: str | None = None, *, now: str | None = None) -> dict[str, Any]:
    with intake_write_lock():
        return _record_client_event_locked(payload, event_type, now=now)


def _record_client_event_locked(
    payload: dict[str, Any],
    event_type: str | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    kind = normalize_space(event_type or payload.get("event_type"), limit=40).lower()
    if kind not in {"view", "start"}:
        raise IntakeError("invalid_event_type", "Only form view and start events are accepted here.")
    submission_id = clean_submission_id(payload.get("submission_id"))
    if not submission_id:
        raise IntakeError("invalid_submission_id", "Missing form session identifier.")
    timestamp = now or utc_now()
    path = EVENT_ROOT / kind / f"{submission_id}.json"
    if path.exists():
        existing = load_json(path, {})
        return {
            "ok": True,
            "event_type": kind,
            "submission_id": submission_id,
            "already_seen": True,
            "event_path": str(path),
            "created_at": existing.get("created_at") or "",
        }
    record = {
        "schema_version": 1,
        "event_type": kind,
        "submission_id": submission_id,
        "created_at": timestamp,
        "attribution": source_attribution(payload),
        "service_slug": service_slug(payload.get("service_interest") or payload.get("workflow_type")),
        "metrics_countable": True,
    }
    write_json(path, record)
    append_jsonl(EVENT_LOG, record)
    build_metrics(write=True)
    return {
        "ok": True,
        "event_type": kind,
        "submission_id": submission_id,
        "already_seen": False,
        "event_path": str(path),
        "created_at": timestamp,
    }


def submit_payload(
    payload: dict[str, Any],
    *,
    now: str | None = None,
    reconcile: bool = True,
    refresh_existing_reports: bool = False,
) -> dict[str, Any]:
    with intake_write_lock():
        return _submit_payload_locked(
            payload,
            now=now,
            reconcile=reconcile,
            refresh_existing_reports=refresh_existing_reports,
        )


def _submit_payload_locked(
    payload: dict[str, Any],
    *,
    now: str | None = None,
    reconcile: bool = True,
    refresh_existing_reports: bool = False,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    normalized = validate_submission_payload(payload)
    existing = existing_submission(normalized["submission_id"])
    if existing:
        if existing.get("dedupe_key") != normalized["dedupe_key"]:
            raise IntakeError("conflicting_submission_id", "This form session has conflicting submission data.", 409)
        return {
            "ok": True,
            "submission_id": existing["submission_id"],
            "status": existing.get("status") or "qualified",
            "duplicate": bool(existing.get("duplicate")),
            "idempotent": True,
            "message": "Already received. No duplicate work was created.",
        }

    dedupe_index = load_dedupe_index()
    duplicate_of = dedupe_index.get(normalized["dedupe_key"]) or normalize_space(payload.get("duplicate_of"), limit=100)
    payload_marked_duplicate = bool(payload.get("duplicate")) or str(payload.get("status") or "").lower() == "duplicate"
    duplicate = payload_marked_duplicate or bool(duplicate_of and duplicate_of != normalized["submission_id"])
    status = "duplicate" if duplicate else "qualified"
    record = {
        "schema_version": 1,
        "submission_id": normalized["submission_id"],
        "dedupe_key": normalized["dedupe_key"],
        "status": status,
        "qualified": not duplicate,
        "duplicate": duplicate,
        "duplicate_of": duplicate_of or "",
        "metrics_countable": not duplicate,
        "source": "public-site-workflow-intake",
        "created_at": timestamp,
        "updated_at": timestamp,
        "contact": {
            "name": normalized["name"],
            "email": normalized["public_business_email"],
            "company": normalized["company"],
        },
        "service_slug": normalized["service_slug"],
        "service_interest": normalized["service_interest"],
        "problem_description": normalized["problem_description"],
        "preferred_next_step": normalized["preferred_next_step"],
        "attribution": normalized["attribution"],
        "paths": {},
        "guardrail": (
            "Internal first-party intake only. No prospect email, public post, purchase, account change, "
            "financial action, or external commitment was made."
        ),
    }

    result: dict[str, Any] = {"qualified": False}
    if reconcile and not duplicate:
        result = sync_record_to_ops_db(record)
        record["qualified"] = bool(result.get("qualified"))
        record["paths"]["inbox_handoff"] = str(result.get("inbox_handoff_path") or "")
        record["account_id"] = result.get("account_id")
        record["contact_id"] = result.get("contact_id")
        record["opportunity_id"] = result.get("opportunity_id")
        record["service_slug"] = str(result.get("service_slug") or record["service_slug"])

    if not duplicate:
        dedupe_index[normalized["dedupe_key"]] = normalized["submission_id"]
        write_dedupe_index(dedupe_index)

    persisted_record = minimal_submission_record(record)
    path = submission_path(persisted_record)
    record["paths"]["submission"] = str(path)
    persisted_record["paths"]["submission"] = str(path)
    write_json(path, persisted_record)
    append_jsonl(EVENT_LOG, {
        "event_type": "submission",
        "submission_id": record["submission_id"],
        "status": record["status"],
        "qualified": record["qualified"],
        "duplicate": record["duplicate"],
        "service_slug": record["service_slug"],
        "created_at": record["created_at"],
    })
    metrics = build_metrics(write=True)
    if refresh_existing_reports:
        refresh_pipeline_reports()
    return {
        "ok": True,
        "submission_id": record["submission_id"],
        "status": record["status"],
        "duplicate": record["duplicate"],
        "idempotent": False,
        "qualified": record["qualified"],
        "opportunity_id": record.get("opportunity_id"),
        "metrics": {
            "completed_submission_count": metrics["completed_submission_count"],
            "qualified_submission_count": metrics["qualified_submission_count"],
        },
        "message": (
            "Already received. No duplicate work was created."
            if duplicate
            else "Received. JVT will review this before any external follow-up."
        ),
    }


def iter_json_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.json") if path.is_file())


def submission_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in iter_json_files(SUBMISSION_ROOT):
        payload = load_json(path, {})
        if isinstance(payload, dict) and payload.get("submission_id"):
            records.append(payload)
    return records


def event_records(kind: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in iter_json_files(EVENT_ROOT / kind):
        payload = load_json(path, {})
        if isinstance(payload, dict) and payload.get("submission_id"):
            records.append(payload)
    return records


def build_metrics(*, write: bool = False) -> dict[str, Any]:
    records = submission_records()
    countable = [item for item in records if item.get("metrics_countable") and not item.get("duplicate")]
    qualified = [item for item in countable if item.get("qualified") and item.get("status") == "qualified"]
    service_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for item in qualified:
        service = str(item.get("service_slug") or "unknown")
        service_counts[service] = service_counts.get(service, 0) + 1
        attribution = item.get("attribution") if isinstance(item.get("attribution"), dict) else {}
        source = str(attribution.get("utm_source") or attribution.get("source") or "direct")
        source_counts[source] = source_counts.get(source, 0) + 1

    report = {
        "generated_at": utc_now(),
        "ok": True,
        "form_view_count": len(event_records("view")),
        "form_start_count": len(event_records("start")),
        "completed_submission_count": len(qualified),
        "qualified_submission_count": len(qualified),
        "duplicate_submission_count": len([item for item in records if item.get("duplicate")]),
        "stored_submission_count": len(records),
        "opportunity_handoff_count": len([item for item in qualified if item.get("opportunity_id")]),
        "inbox_handoff_count": len([item for item in qualified if (item.get("paths") or {}).get("inbox_handoff")]),
        "service_interest_counts": dict(sorted(service_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "latest_submissions": [
            {
                "submission_id": item.get("submission_id"),
                "created_at": item.get("created_at"),
                "company": (item.get("contact") or {}).get("company"),
                "service_slug": item.get("service_slug"),
                "status": item.get("status"),
                "duplicate": bool(item.get("duplicate")),
                "opportunity_id": item.get("opportunity_id"),
            }
            for item in sorted(records, key=lambda value: str(value.get("created_at") or ""), reverse=True)[:10]
        ],
        "paths": {
            "data_root": str(DATA_ROOT),
            "submissions": str(SUBMISSION_ROOT),
            "events": str(EVENT_ROOT),
            "dedupe_index": str(DEDUP_INDEX),
            "state_json": str(REPORT_JSON),
            "state_markdown": str(REPORT_MD),
        },
        "guardrail": "First-party intake visibility only. No sends, spend, public posting, account changes, or external commitments.",
    }
    if write:
        write_json(REPORT_JSON, report)
        write_metrics_markdown(report)
    return report


def write_metrics_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Public Conversion Intake",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Form views: `{report['form_view_count']}`",
        f"- Form starts: `{report['form_start_count']}`",
        f"- Completed submissions: `{report['completed_submission_count']}`",
        f"- Qualified submissions: `{report['qualified_submission_count']}`",
        f"- Duplicate submissions: `{report['duplicate_submission_count']}`",
        f"- Opportunity handoffs: `{report['opportunity_handoff_count']}`",
        f"- Inbox handoffs: `{report['inbox_handoff_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "## Service Interest",
        "",
    ]
    service_counts = report.get("service_interest_counts") or {}
    if not service_counts:
        lines.append("- None yet.")
    for slug, count in sorted(service_counts.items()):
        lines.append(f"- `{slug}`: {count}")
    lines.extend(["", "## Latest Submissions", ""])
    latest = report.get("latest_submissions") or []
    if not latest:
        lines.append("- None yet.")
    for item in latest:
        lines.append(
            f"- `{item.get('status')}` {item.get('company') or 'Unknown'} / "
            f"`{item.get('service_slug') or 'unknown'}` / `{item.get('submission_id')}`"
        )
    REPORT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def refresh_pipeline_reports() -> None:
    try:
        import opportunity_manager

        opportunity_manager.main()
    except Exception:
        pass
    try:
        import conversion_pipeline

        conversion_pipeline.build_report()
    except Exception:
        pass


def parse_request_body(headers: dict[str, str], body: bytes) -> dict[str, Any]:
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type.startswith("multipart/"):
        raise IntakeError("attachments_not_allowed", "File uploads are not accepted.", 415)
    if content_type in {"", "application/json"}:
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise IntakeError("invalid_json", "Request body must be valid JSON.") from exc
        return payload if isinstance(payload, dict) else {}
    if content_type == "application/x-www-form-urlencoded":
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}
    raise IntakeError("unsupported_content_type", "Submit JSON or form data only.", 415)


class IntakeHandler(BaseHTTPRequestHandler):
    server_version = "JVTIntake/0.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"ok": True})

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] in {"/health", "/api/public-conversion-intake/status"}:
            self._send_json(200, build_metrics(write=True))
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/workflow-intake":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("content-length") or "0")
            payload = parse_request_body({key.lower(): value for key, value in self.headers.items()}, self.rfile.read(length))
            event_type = normalize_space(payload.get("event_type"), limit=40).lower()
            if event_type in {"view", "start"}:
                result = record_client_event(payload, event_type)
            else:
                result = submit_payload(payload, refresh_existing_reports=True)
        except IntakeError as exc:
            append_jsonl(EVENT_LOG, {
                "event_type": "rejected_submission",
                "code": exc.code,
                "created_at": utc_now(),
            })
            self._send_json(exc.status_code, {"ok": False, "error": exc.code, "message": exc.message})
            return
        self._send_json(200, result)

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), IntakeHandler)
    print(json.dumps({"ok": True, "url": f"http://{host}:{port}", "endpoint": "/api/workflow-intake"}))
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture and reconcile first-party public workflow intake.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("--payload-json", required=True)
    submit_parser.add_argument("--no-reconcile", action="store_true")
    submit_parser.add_argument("--refresh-reports", action="store_true")

    event_parser = subparsers.add_parser("event")
    event_parser.add_argument("--event-type", choices=["view", "start"], required=True)
    event_parser.add_argument("--payload-json", required=True)

    subparsers.add_parser("metrics")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8094)

    args = parser.parse_args()
    if args.command == "submit":
        payload = load_json(Path(args.payload_json), {})
        print(json.dumps(
            submit_payload(payload, reconcile=not args.no_reconcile, refresh_existing_reports=args.refresh_reports),
            indent=2,
        ))
    elif args.command == "event":
        payload = load_json(Path(args.payload_json), {})
        print(json.dumps(record_client_event(payload, args.event_type), indent=2))
    elif args.command == "metrics":
        print(json.dumps(build_metrics(write=True), indent=2))
    elif args.command == "serve":
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
