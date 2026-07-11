#!/usr/bin/env python3
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

BAD_LOCAL_PARTS = {
    "abuse",
    "career",
    "careers",
    "donotreply",
    "do-not-reply",
    "employment",
    "example",
    "hr",
    "jobs",
    "marketing",
    "no-reply",
    "noreply",
    "privacy",
    "recruit",
    "recruiter",
    "recruiting",
    "resumes",
    "seo",
    "support+test",
    "talent",
    "test",
    "user",
    "webmaster",
}

PUBLIC_BUSINESS_LOCAL_PARTS = {
    "admin",
    "appointments",
    "billing",
    "clientservices",
    "concierge",
    "contact",
    "frontdesk",
    "hello",
    "info",
    "inquiries",
    "intake",
    "office",
    "operations",
    "ops",
    "patients",
    "reception",
    "scheduling",
    "service",
    "support",
}

FREE_EMAIL_DOMAINS = {
    "aol.com",
    "gmail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "me.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}

PLACEHOLDER_DOMAINS = {
    "domain.com",
    "example.com",
    "localhost",
    "test.com",
}

GENERIC_NAME_PATTERNS = (
    re.compile(r"^about\b", re.I),
    re.compile(r"^contact\b", re.I),
    re.compile(r"^home(?:\s+page)?$", re.I),
    re.compile(r"\b(?:top|best|top-rated|near me)\b", re.I),
    re.compile(r"\b(?:dentist|doctor|chiropractor|plumber|plumbing|hvac|electrician|mortgage broker|lawyer|attorney|clinic|accountant|cpa)\s+in\b", re.I),
    re.compile(r"\bservices?\s+in\s+[a-z ,]+$", re.I),
    re.compile(r"\b(bookkeeping|payroll|tax)\s+services?\s+(?:in|for)\b", re.I),
    re.compile(r"\b(websites?|software platform|saas|practice management software)\b", re.I),
    re.compile(r"\b(calculators?|free\s+(?:finance|health|academic)|online\s+tools?)\b", re.I),
    re.compile(r"\b(directory|marketplace|portal)\b", re.I),
    re.compile(r"\b(?:leading|premier|trusted)\s+(?:accounting|cpa|law|dental|roofing|construction|insurance)\b", re.I),
)

TARGET_INDUSTRIES = {
    "Accounting / Tax Firm",
    "Dental / Healthcare Admin",
    "Home Services",
    "Insurance Agency",
    "IT / Ballot Services",
    "Law Firm",
    "Property Management",
    "Mortgage / Title Services",
    "Construction / Contracting",
}

LANE_KEYWORDS = {
    "Accounting / Tax Firm": ("tax", "account", "bookkeep", "payroll", "client", "document", "workflow"),
    "Dental / Healthcare Admin": ("dental", "dentist", "patient", "appointment", "insurance", "intake", "voice", "front desk"),
    "Home Services": ("service", "dispatch", "estimate", "quote", "appointment", "plumbing", "hvac", "electrical"),
    "Insurance Agency": ("insurance", "policy", "claim", "certificate", "coi", "commercial lines", "risk"),
    "IT / Ballot Services": ("ballot", "election", "board", "meeting", "hoa", "condo", "association", "av"),
    "Law Firm": ("law", "legal", "attorney", "client", "matter", "intake", "document"),
    "Property Management": ("property", "tenant", "lease", "maintenance", "hoa", "association", "board"),
    "Mortgage / Title Services": ("mortgage", "title", "closing", "payoff", "loan", "document"),
    "Construction / Contracting": ("construction", "contract", "rfi", "submittal", "bid", "project"),
}


def root_domain(value: str) -> str:
    value = value.lower().strip().removeprefix("www.").split(":", 1)[0]
    parts = [part for part in value.split(".") if part]
    if len(parts) < 2:
        return value
    return ".".join(parts[-2:])


def host_from_url(value: str) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value if "://" in value else f"https://{value}")
    return (parsed.netloc or parsed.path.split("/", 1)[0]).lower().strip()


def is_placeholder_domain(value: str) -> bool:
    clean = value.lower().strip().removeprefix("www.").split(":", 1)[0]
    if not clean:
        return False
    return clean in PLACEHOLDER_DOMAINS or clean.endswith(".example") or root_domain(clean) in PLACEHOLDER_DOMAINS


def source_url(payload: dict[str, Any]) -> str:
    for key in ("contact_page", "website", "site_url", "source_url", "homepage"):
        raw = str(payload.get(key) or "").strip()
        if raw:
            return raw
    urls = payload.get("manual_verified_source_urls")
    if isinstance(urls, list) and urls:
        return str(urls[0] or "").strip()
    return ""


def clean_text(*values: Any) -> str:
    return " ".join(re.sub(r"\s+", " ", str(value or "")).strip() for value in values if str(value or "").strip()).lower()


def lane_fit(payload: dict[str, Any]) -> tuple[bool, str]:
    industry = str(payload.get("industry") or "").strip()
    context = clean_text(
        payload.get("company_name"),
        payload.get("industry"),
        payload.get("practice_area"),
        payload.get("lead_context"),
        payload.get("public_context"),
        payload.get("likely_pain"),
        payload.get("personalized_offer"),
        payload.get("fit_reason"),
        payload.get("notes"),
    )
    if industry not in TARGET_INDUSTRIES:
        return False, f"off-target or missing industry: {industry or 'missing'}"
    keywords = LANE_KEYWORDS.get(industry) or ()
    if any(keyword in context for keyword in keywords):
        return True, f"{industry} context matches lane terms"
    return False, f"{industry} lacks concrete lane-fit evidence"


def recipient_kind(local: str) -> str:
    local = local.lower().strip()
    if local in PUBLIC_BUSINESS_LOCAL_PARTS:
        return "public_business_inbox"
    if any(token in local for token in ("owner", "partner", "ops", "office", "intake", "appoint", "schedule")):
        return "relevant_role_inbox"
    if re.fullmatch(r"[a-z][a-z.'_-]{1,28}", local) or re.fullmatch(r"[a-z][a-z.'_-]+[._-][a-z][a-z.'_-]+", local):
        return "named_business_contact"
    return "unclassified_recipient"


def lead_payload(source: Any) -> dict[str, Any]:
    """Normalize sqlite rows or queue metadata into the evidence-gate contract."""
    if hasattr(source, "keys"):
        data = {key: source[key] for key in source.keys()}
    else:
        data = dict(source or {})
    notes = str(data.get("notes") or "").strip()
    fit_reason = str(data.get("fit_reason") or "").strip() or notes
    return {
        "company_name": data.get("company_name"),
        "recipient_email": data.get("recipient_email") or data.get("public_email"),
        "public_email": data.get("public_email") or data.get("recipient_email"),
        "contact_page": data.get("contact_page") or data.get("website"),
        "website": data.get("website") or data.get("source_url"),
        "industry": data.get("industry"),
        "practice_area": data.get("practice_area"),
        "notes": notes,
        "fit_reason": fit_reason,
        "public_context": data.get("public_context") or notes,
        "likely_pain": data.get("likely_pain"),
        "personalized_offer": data.get("personalized_offer"),
        "manual_verified_public_contact_at": data.get("manual_verified_public_contact_at"),
        "manual_verified_source_urls": data.get("manual_verified_source_urls"),
    }


def evidence_gate(payload: dict[str, Any], *, require_business_inbox: bool = False) -> tuple[list[str], dict[str, Any]]:
    reasons: list[str] = []
    company = str(payload.get("company_name") or "").strip()
    email = str(payload.get("recipient_email") or payload.get("public_email") or "").strip().lower()
    src = source_url(payload)
    host = host_from_url(src)
    manual_verified = bool(payload.get("manual_verified_public_contact_at") and payload.get("manual_verified_source_urls"))

    if not src or not host:
        reasons.append("missing public source/contact URL")
    elif is_placeholder_domain(host):
        reasons.append("placeholder/test public source domain")
    if not company:
        reasons.append("missing company name")
    elif len(company.split()) > 9:
        reasons.append("company name too long to trust automatically")
    elif any(pattern.search(company) for pattern in GENERIC_NAME_PATTERNS):
        reasons.append("generic/page-title company name")

    local = ""
    domain = ""
    kind = "missing"
    if not EMAIL_RE.match(email):
        reasons.append("invalid recipient email")
    else:
        local, domain = email.rsplit("@", 1)
        kind = recipient_kind(local)
        if is_placeholder_domain(domain):
            reasons.append("placeholder/test recipient domain")
        if local in BAD_LOCAL_PARTS or any(token in local for token in ("career", "recruit", "resume", "noreply", "no-reply")):
            reasons.append("blocked or unrelated recipient local part")
        if domain in FREE_EMAIL_DOMAINS and not manual_verified:
            reasons.append("free-mail recipient requires manual source verification")
        if host and root_domain(host) != root_domain(domain) and not manual_verified:
            reasons.append("email domain does not match public source domain")
        if require_business_inbox and kind not in {"public_business_inbox", "relevant_role_inbox"} and not manual_verified:
            reasons.append("recipient is not a public business or relevant operations inbox")

    fit_ok, fit_reason = lane_fit(payload)
    if not fit_ok and not manual_verified:
        reasons.append(fit_reason)

    why_parts = [
        str(payload.get("likely_pain") or "").strip(),
        str(payload.get("personalized_offer") or "").strip(),
        str(payload.get("fit_reason") or "").strip(),
        str(payload.get("public_context") or "").strip(),
        str(payload.get("notes") or "").strip(),
    ]
    why_now = next((part for part in why_parts if len(part) >= 35), "")
    if not why_now and not manual_verified:
        reasons.append("missing why-this-recipient-now evidence")

    severe_prefixes = (
        "invalid",
        "missing",
        "placeholder",
        "blocked",
        "email domain",
        "free-mail",
        "generic",
        "off-target",
    )
    severity = "pass"
    if reasons:
        severity = "hard_hold" if any(reason.startswith(severe_prefixes) for reason in reasons) else "review"
    score = max(0, 100 - (45 if severity == "review" else 0) - (90 if severity == "hard_hold" else 0))

    evidence = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": src,
        "source_domain": host,
        "company_name": company,
        "recipient_email": email,
        "recipient_local_part": local,
        "recipient_domain": domain,
        "recipient_kind": kind,
        "domain_aligned": bool(host and domain and root_domain(host) == root_domain(domain)),
        "manual_verified": manual_verified,
        "industry": str(payload.get("industry") or "").strip(),
        "lane_fit": fit_ok,
        "lane_fit_reason": fit_reason,
        "why_this_recipient_now": why_now[:500],
        "decision": "pass" if not reasons else "hold",
        "severity": severity,
        "score": score,
        "hold_reasons": reasons,
    }
    return reasons, evidence


def stamp_evidence(payload: dict[str, Any], evidence: dict[str, Any]) -> None:
    payload["recipient_evidence"] = evidence
    if evidence.get("decision") == "pass":
        payload["recipient_evidence_verified_at"] = evidence.get("generated_at")
