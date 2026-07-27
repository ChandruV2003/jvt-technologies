from __future__ import annotations

import os
from email.utils import parseaddr
from typing import Any


DEFAULT_INTERNAL_EMAILS = {
    "chandruvasu@icloud.com",
    "chandruv@icloud.com",
    "jvtvasu@icloud.com",
    "chandru@jvt-technologies.com",
    "chandruv@jvt-technologies.com",
    "hello@jvt-technologies.com",
}

SYSTEM_SENDER_TERMS = {
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
}


def internal_emails() -> set[str]:
    raw = os.environ.get("JVT_OPERATOR_EMAILS", "")
    configured = {value.strip().lower() for value in raw.split(",") if value.strip()}
    return DEFAULT_INTERNAL_EMAILS | configured


def sender_email(payload_or_sender: dict[str, Any] | str) -> str:
    if isinstance(payload_or_sender, dict):
        raw = str(
            payload_or_sender.get("from")
            or payload_or_sender.get("sender")
            or payload_or_sender.get("sender_email")
            or ""
        )
    else:
        raw = payload_or_sender
    parsed = parseaddr(raw)[1].lower().strip()
    return parsed or raw.lower().strip()


def sender_domain(email_address: str) -> str:
    return email_address.rsplit("@", 1)[-1].lower().strip() if "@" in email_address else ""


def is_internal_sender(email_address: str) -> bool:
    value = email_address.lower().strip()
    return value in internal_emails() or value.endswith("@jvt-technologies.com")


def is_system_sender(email_address: str) -> bool:
    value = email_address.lower().strip()
    domain = sender_domain(value)
    return any(term in value or term in domain for term in SYSTEM_SENDER_TERMS)


def qualified_external_inbound(payload: dict[str, Any]) -> bool:
    email_address = sender_email(payload)
    if not email_address or is_internal_sender(email_address) or is_system_sender(email_address):
        return False
    agent_status = str(payload.get("agent_triage_status") or "").lower()
    if agent_status.startswith(("closed_", "reviewed_internal")):
        return False
    bucket = str(payload.get("triage_bucket") or "").lower()
    priority = str(payload.get("triage_priority") or "").lower()
    action = str(payload.get("triage_action") or "").lower()
    return bucket == "direct" or priority == "high" or action == "review"
