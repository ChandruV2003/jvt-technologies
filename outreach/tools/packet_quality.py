#!/usr/bin/env python3
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recipient_quality import evidence_gate, stamp_evidence


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PLACEHOLDER_PATTERNS = (
    re.compile(r"\{\{.+?\}\}"),
    re.compile(r"\[[A-Z0-9_ -]{3,}\]"),
    re.compile(r"\b(TODO|TBD|INSERT|FILL IN)\b", re.I),
)
EXACT_BAD_NAMES = {
    "academy of general dentistry",
    "accounting firm",
    "accounting services",
    "ata cpa contact",
    "austin, texas bookkeeping, payroll & tax services firm",
    "charlotte nc cpa",
    "contact us",
    "cpa accountant",
    "cpa accounting",
    "cpa el paso tx",
    "dentist in fort myers, fl",
    "ep cpa",
    "home page",
    "lb cpa",
    "mycalculators.us – free finance, health & academic calculators",
    "online bookkeeping & payroll for small business",
    "outsourced bookkeeping and controller services",
    "property management",
    "small businesses tax management & bookkeeping services",
    "tax advisory services",
    "top mortgage broker in new york, ny",
    "wealth management",
}
GENERIC_NAME_PATTERNS = (
    re.compile(r"^about\b", re.I),
    re.compile(r"^cpa\b", re.I),
    re.compile(r"^(?:accounting firm|property management|tax advisory services)$", re.I),
    re.compile(r"\b(?:top|best|top-rated|near me)\b", re.I),
    re.compile(r"\b(?:dentist|doctor|chiropractor|plumber|plumbing|hvac|electrician|mortgage broker|lawyer|attorney|clinic|accountant|cpa)\s+in\b", re.I),
    re.compile(r"\b(?:accounting|cpa|law)\s+firm\s+for\b", re.I),
    re.compile(r"\bcpa firm in\b", re.I),
    re.compile(r"\bbookkeeping .* for small business\b", re.I),
    re.compile(r"\b(?:accounting|cpa) payroll tax\b", re.I),
    re.compile(r"\bservices?\s+in\s+[a-z ,]+$", re.I),
    re.compile(r"\b(calculators?|free\s+(?:finance|health|academic)|online\s+tools?)\b", re.I),
    re.compile(r"\bwebsites?\b", re.I),
    re.compile(r"^[A-Z][A-Za-z .'-]+,?\s+[A-Z]{2}\s+(?:accounting|bookkeeping|payroll|tax)\b", re.I),
    re.compile(r":\s+.*\b(?:accounting|bookkeeping|cpa|law|roofing|tax)\s+firm\b", re.I),
    re.compile(r"\s+-\s+CPA\s+[A-Za-z ]+$", re.I),
    re.compile(r"\bexperts?\s+[l|]\s+[A-Z]", re.I),
    re.compile(r"\s[-|–—]\s*$", re.I),
)
PAGE_TITLE_TAGLINE_PATTERNS = (
    re.compile(r"\.\s+(?:one|a|the|your|our)\b.+$", re.I),
    re.compile(r":\s+(?:global|expert|trusted|maximize|online|outsourced)\b.+$", re.I),
    re.compile(r"\s+-\s+(?:one|a|the|your|our|expert|trusted|maximize|online|outsourced)\b.+$", re.I),
)
PAGE_TITLE_PHRASES = (
    "one law firm, diverse solutions",
    "expert tax services at your fingertips",
    "global business process outsourcing",
    "online bookkeeping & payroll",
    "outsourced accounting",
    "outsourced bookkeeping",
)
OFF_TARGET_NAME_TERMS = (
    "outsourcing",
    "outsourced",
    "business process outsourcing",
    " bpo ",
    "bpo company",
)
SOFTWARE_PLATFORM_PATTERNS = (
    re.compile(r"\bsoftware platform\b", re.I),
    re.compile(r"\bpractice management software\b", re.I),
    re.compile(r"\bbusiness management software\b", re.I),
    re.compile(r"\bworkflow software\b", re.I),
    re.compile(r"\bsaas\b", re.I),
    re.compile(r"\bplatform for\b", re.I),
    re.compile(r"\bjetpack workflow\b", re.I),
)
POLLUTED_LOCATION_PATTERNS = (
    re.compile(r"\bour expertise\b", re.I),
    re.compile(r"\bprovides small business\b", re.I),
    re.compile(r"\bfrom our offices\b", re.I),
    re.compile(r"\bwe have professional\b", re.I),
    re.compile(r"\bhas served the\b", re.I),
    re.compile(r"\bgreater [A-Z][A-Za-z .'-]+,\s*[A-Z]{2}\b"),
)
RECRUITING_PATH_RE = re.compile(r"/(careers?|employment|jobs?|recruiting|talent)(?:/|$)", re.I)
WEIRD_CPA_NAME_RE = re.compile(r"^[A-Z][A-Za-z]+ Cpa$")

BLOCKED_LOCAL_PARTS = {
    "career",
    "careers",
    "employment",
    "example",
    "hr",
    "jobs",
    "marketing",
    "no-reply",
    "noreply",
    "recruit",
    "recruiter",
    "recruiting",
    "resumes",
    "seo",
    "talent",
    "test",
    "user",
    "webmaster",
}
SUSPICIOUS_LOCAL_PARTS = {"adminuser", "lehuser"}
TARGET_INDUSTRIES = {
    "Accounting / Tax Firm",
    "Construction / Contracting",
    "Dental / Healthcare Admin",
    "Home Services",
    "Insurance Agency",
    "IT / Ballot Services",
    "Law Firm",
    "Mortgage / Title Services",
    "Property Management",
}
HEALTH_NAME_TERMS = ("health", "chiro", "chiropractic", "dental", "dentistry", "clinic", "medical")
DOMAIN_GENERIC_TOKENS = {
    "accounting",
    "agency",
    "association",
    "commercial",
    "company",
    "contact",
    "dental",
    "dentistry",
    "firm",
    "general",
    "group",
    "health",
    "home",
    "insurance",
    "law",
    "management",
    "office",
    "property",
    "roofing",
    "services",
    "the",
}
ORG_HINT_RE = re.compile(
    r"\b(llc|llp|pllc|pc|p\.c\.|inc|corp|company|associates|group|law|cpa|dental|dentistry|agency|management|services)\b",
    re.I,
)

HARD_HOLD_CODES = {
    "blocked_recipient",
    "careers_contact_page",
    "cross_lane_ballot_offer",
    "cross_lane_dental_offer",
    "cross_lane_healthcare_offer",
    "email_domain_mismatch",
    "internal_recipient",
    "internal_test_company",
    "invalid_recipient_email",
    "off_target_industry",
    "off_target_outsourcing",
    "recipient_evidence_hard_hold",
    "recruiting_recipient",
    "software_platform_target",
}
REASON_WEIGHTS = {
    "recipient_evidence_hard_hold": 90,
    "invalid_recipient_email": 100,
    "internal_recipient": 100,
    "internal_test_company": 100,
    "off_target_outsourcing": 85,
    "software_platform_target": 80,
    "recruiting_recipient": 80,
    "careers_contact_page": 80,
    "email_domain_mismatch": 70,
    "cross_lane_dental_offer": 70,
    "cross_lane_healthcare_offer": 70,
    "cross_lane_ballot_offer": 70,
    "generic_company_name": 45,
    "company_identity_domain_mismatch": 45,
    "company_name_too_long": 35,
    "missing_rendered_artifact": 45,
    "short_text_body": 30,
    "missing_subject": 40,
    "historical_quality_hold": 35,
}


def _root_domain(value: str) -> str:
    clean = value.lower().strip().removeprefix("www.").split(":", 1)[0]
    parts = [part for part in clean.split(".") if part]
    return ".".join(parts[-2:]) if len(parts) >= 2 else clean


def _host_from_url(value: str) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value if "://" in value else f"https://{value}")
    return (parsed.netloc or parsed.path.split("/", 1)[0]).lower().strip()


def _strip_page_title_tagline(name: str) -> str:
    candidate = re.sub(r"\s+", " ", name).strip(" -|,")
    for pattern in PAGE_TITLE_TAGLINE_PATTERNS:
        cleaned = pattern.sub("", candidate).strip(" -|,")
        if cleaned and cleaned != candidate and ORG_HINT_RE.search(cleaned):
            return cleaned
    return candidate


def _has_page_title_tagline(name: str) -> bool:
    lowered = name.lower()
    return any(phrase in lowered for phrase in PAGE_TITLE_PHRASES) or (
        _strip_page_title_tagline(name) != re.sub(r"\s+", " ", name).strip(" -|,")
    )


def _meaningful_tokens(value: str) -> set[str]:
    raw = re.split(r"[^a-z0-9]+", value.lower())
    tokens = {token for token in raw if len(token) >= 4 and token not in DOMAIN_GENERIC_TOKENS}
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    for generic in sorted(DOMAIN_GENERIC_TOKENS, key=len, reverse=True):
        compact = compact.replace(generic, " ")
    tokens.update(token for token in compact.split() if len(token) >= 4 and token not in DOMAIN_GENERIC_TOKENS)
    return tokens


def _has_name_domain_overlap(name: str, host: str) -> bool:
    host_root = _root_domain(host).split(".", 1)[0]
    name_tokens = _meaningful_tokens(name)
    host_tokens = _meaningful_tokens(host_root)
    if not name_tokens or not host_tokens:
        return False
    host_compact = re.sub(r"[^a-z0-9]+", "", host_root.lower())
    name_compact = re.sub(r"[^a-z0-9]+", "", name.lower())
    return bool(name_tokens & host_tokens) or any(token in host_compact for token in name_tokens) or any(
        token in name_compact for token in host_tokens
    )


def _is_followup(payload: dict[str, Any]) -> bool:
    return bool(payload.get("follow_up_stage") or payload.get("follow_up_parent_stem"))


def _artifact_exists(value: Any) -> bool:
    raw = str(value or "").strip()
    return bool(raw and Path(raw).is_file())


def _read_artifact(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _reason_code(reason: str) -> str:
    normalized = reason.lower()
    if normalized.startswith("invalid recipient"):
        return "invalid_recipient_email"
    if "blocked or unrelated recipient" in normalized:
        return "blocked_recipient"
    if "free-mail recipient" in normalized:
        return "unverified_free_mail_recipient"
    if "email domain does not match" in normalized:
        return "email_domain_mismatch"
    if "placeholder" in normalized:
        return "placeholder_source_or_recipient"
    if "generic/page-title" in normalized:
        return "generic_company_name"
    if "company name too long" in normalized:
        return "company_name_too_long"
    if "off-target" in normalized:
        return "off_target_industry"
    if "missing public source" in normalized:
        return "missing_public_source"
    if "missing company name" in normalized:
        return "missing_company_name"
    if "missing why-this-recipient-now" in normalized:
        return "missing_recipient_fit_evidence"
    if "recipient is not a public business" in normalized:
        return "recipient_role_unverified"
    return "recipient_evidence_hold"


def _historical_hold_is_recheckable(value: str) -> bool:
    normalized = re.sub(r"(?:existing quality hold:\s*)+", "", value, flags=re.I).strip().lower()
    if not normalized:
        return False
    recheckable_markers = (
        "manual review required after copy regeneration",
        "manual review required after dental-copy regeneration",
        "manual review required after source/search repair",
        "stale quality hold",
    )
    unsafe_markers = (
        "auto-send hold",
        "blocked",
        "company name",
        "conflicting",
        "do not approve",
        "domain",
        "false positive",
        "generic",
        "mismatch",
        "off-target",
        "page-title",
        "recruit",
        "suspicious",
        "wrong",
    )
    return any(marker in normalized for marker in recheckable_markers) and not any(
        marker in normalized for marker in unsafe_markers
    )


def classify_packet(
    payload: dict[str, Any],
    *,
    source_queue: str = "review",
    strict_historical_hold: bool = False,
) -> dict[str, Any]:
    reasons: list[tuple[str, str]] = []

    def add(code: str, reason: str) -> None:
        if code not in {existing_code for existing_code, _ in reasons}:
            reasons.append((code, reason))

    company = str(payload.get("company_name") or "").strip()
    lower_company = company.lower()
    email = str(payload.get("recipient_email") or payload.get("public_email") or "").strip().lower()
    contact_page = str(payload.get("contact_page") or payload.get("website") or "").strip()
    industry = str(payload.get("industry") or "").strip()
    practice = str(payload.get("practice_area") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    offer = str(payload.get("personalized_offer") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    city_state = str(payload.get("city_state") or "").strip()
    historical_hold = str(payload.get("quality_hold_reason") or "").strip()
    manual_verified = bool(payload.get("manual_verified_public_contact_at") and payload.get("manual_verified_source_urls"))
    kind = "followup" if _is_followup(payload) else "initial"

    evidence_reasons, evidence = evidence_gate(payload)
    for evidence_reason in evidence_reasons:
        code = _reason_code(evidence_reason)
        add(code, evidence_reason)
    if evidence_reasons and str(evidence.get("severity") or "") == "hard_hold":
        add("recipient_evidence_hard_hold", "recipient/source evidence failed a hard safety gate")

    if not company:
        add("missing_company_name", "missing company name")
    if len(company.split()) > 9 and not manual_verified:
        add("company_name_too_long", "company name too long to trust automatically")
    if lower_company in EXACT_BAD_NAMES and not manual_verified:
        add("generic_company_name", "generic/page-title company name")
    if (_has_page_title_tagline(company) or any(pattern.search(company) for pattern in GENERIC_NAME_PATTERNS)) and not manual_verified:
        add("generic_company_name", "generic/page-title company name")
    if "jvt technologies" in lower_company or lower_company == "test":
        add("internal_test_company", "internal/test company")
    if any(term in f" {lower_company} " for term in OFF_TARGET_NAME_TERMS):
        add("off_target_outsourcing", "off-target outsourcing/BPO company category")
    if WEIRD_CPA_NAME_RE.match(company):
        add("unnormalized_company_name", "likely unnormalized CPA name")

    if not EMAIL_RE.match(email):
        add("invalid_recipient_email", "invalid recipient email")
    else:
        local, domain = email.rsplit("@", 1)
        if local in BLOCKED_LOCAL_PARTS or any(token in local for token in ("career", "recruit", "resume")):
            add("blocked_recipient", "blocked or unrelated recipient local part")
        if local in SUSPICIOUS_LOCAL_PARTS or local.endswith("user"):
            add("suspicious_recipient", "suspicious email local part")
        if email.endswith("@jvt-technologies.com"):
            add("internal_recipient", "internal recipient")
        parsed = urllib.parse.urlparse(contact_page if "://" in contact_page else f"https://{contact_page}") if contact_page else None
        if parsed and RECRUITING_PATH_RE.search(parsed.path or ""):
            add("careers_contact_page", "careers/recruiting contact page")
        if local in {"career", "careers", "employment", "hr", "jobs", "recruit", "recruiter", "recruiting", "resumes", "talent"}:
            add("recruiting_recipient", "recruiting/careers contact, not business operations inbox")
        host = _host_from_url(contact_page)
        if host and _root_domain(host) != _root_domain(domain) and not manual_verified:
            add("email_domain_mismatch", "email domain does not match contact page domain")
        elif host and company and not _has_name_domain_overlap(_strip_page_title_tagline(company), host) and not manual_verified:
            add("company_identity_domain_mismatch", "company name does not clearly match contact domain")

    if industry and industry not in TARGET_INDUSTRIES:
        add("off_target_industry", f"off-target industry: {industry}")
    if industry == "Property Management" and any(term in lower_company for term in HEALTH_NAME_TERMS) and not manual_verified:
        add("industry_identity_mismatch", "company name looks health/dental-related but industry is property management")

    offer_lower = offer.lower()
    if "dental voice intake" in offer_lower and industry != "Dental / Healthcare Admin" and not manual_verified:
        add("cross_lane_dental_offer", "offer copy is dental-specific but target industry is not dental/healthcare")
    if any(term in offer_lower for term in ("medical advice", "confirming appointments", "patient")) and industry != "Dental / Healthcare Admin" and not manual_verified:
        add("cross_lane_healthcare_offer", "offer copy uses healthcare appointment/medical language outside the healthcare lane")
    if "election-sensitive" in offer_lower and industry not in {"IT / Ballot Services", "Property Management"} and not manual_verified:
        add("cross_lane_ballot_offer", "offer copy references ballot/election workflow outside the ballot/property lane")

    target_context = "\n".join([company, industry, practice, contact_page, notes])
    if any(pattern.search(target_context) for pattern in SOFTWARE_PLATFORM_PATTERNS):
        add("software_platform_target", "software/SaaS platform target, not a service buyer")
    if any(pattern.search(city_state) for pattern in POLLUTED_LOCATION_PATTERNS):
        add("polluted_location_text", "location field contains scraped page text")

    artifacts = {
        "review_path": _artifact_exists(payload.get("review_path")),
        "text_path": _artifact_exists(payload.get("text_path")),
        "html_path": _artifact_exists(payload.get("html_path")),
    }
    if source_queue in {"review", "approved"}:
        if not artifacts["text_path"] or not artifacts["html_path"]:
            add("missing_rendered_artifact", "missing rendered message artifact")
        text_body = _read_artifact(payload.get("text_path"))
        html_body = _read_artifact(payload.get("html_path"))
        if text_body and len(text_body.strip()) < 350:
            add("short_text_body", "rendered text body is too short")
        if not subject:
            add("missing_subject", "missing subject")
        elif len(subject) > 110:
            add("subject_too_long", "subject is longer than 110 characters")
        combined = "\n".join([subject, text_body, html_body])
        if any(pattern.search(combined) for pattern in PLACEHOLDER_PATTERNS):
            add("unresolved_placeholder", "rendered message contains an unresolved placeholder")
        if "unsubscribe" in combined.lower():
            add("bulk_unsubscribe_language", "rendered message contains bulk unsubscribe language")

    current_reason_codes = [code for code, _ in reasons]
    historical_hold_only = bool(historical_hold and not current_reason_codes)
    safe_to_clear_quality_hold = bool(
        historical_hold_only
        and not strict_historical_hold
        and _historical_hold_is_recheckable(historical_hold)
    )
    if historical_hold and (strict_historical_hold or (historical_hold_only and not safe_to_clear_quality_hold)):
        add("historical_quality_hold", f"existing quality hold: {historical_hold}")

    reason_codes = [code for code, _ in reasons]
    human_reasons = [reason for _, reason in reasons]
    has_hard_hold = any(code in HARD_HOLD_CODES for code in reason_codes) or (
        bool(evidence_reasons) and str(evidence.get("severity") or "") == "hard_hold"
    )
    if has_hard_hold:
        decision = "hard_hold"
    elif reason_codes:
        decision = "repair_candidate"
    else:
        decision = "approval_candidate"

    score = max(0, 100 - sum(REASON_WEIGHTS.get(code, 20) for code in reason_codes))
    result = {
        "decision": decision,
        "score": score,
        "reason_codes": reason_codes,
        "human_reasons": human_reasons,
        "recipient_evidence": evidence,
        "artifacts": artifacts,
        "kind": kind,
        "historical_hold": historical_hold,
        "historical_hold_only": historical_hold_only,
        "safe_to_clear_quality_hold": safe_to_clear_quality_hold,
        "source_queue": source_queue,
    }
    return result


def is_auto_approval_candidate(result: dict[str, Any]) -> bool:
    """Return true only when the canonical classifier found no active blocker."""

    return result.get("decision") == "approval_candidate" and not result.get("human_reasons")


def stamp_packet_quality(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    stamp_evidence(payload, result.get("recipient_evidence") or {})
    payload["packet_quality"] = {
        key: result.get(key)
        for key in (
            "decision",
            "score",
            "reason_codes",
            "human_reasons",
            "artifacts",
            "kind",
            "historical_hold_only",
            "safe_to_clear_quality_hold",
            "source_queue",
        )
    }
    return payload


def clear_safe_historical_hold(
    payload: dict[str, Any],
    result: dict[str, Any],
    *,
    source: str,
) -> bool:
    hold = str(payload.get("quality_hold_reason") or "").strip()
    if not hold or not result.get("safe_to_clear_quality_hold"):
        return False
    history = payload.get("quality_hold_history")
    if not isinstance(history, list):
        history = []
    already_recorded = any(
        (isinstance(item, dict) and str(item.get("reason") or "").strip() == hold)
        or (isinstance(item, str) and item.strip() == hold)
        for item in history
    )
    resolved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not already_recorded:
        history.append(
            {
                "reason": hold,
                "resolved_at": resolved_at,
                "resolution": "current canonical classifier found no active blocker",
                "source": source,
            }
        )
    payload["quality_hold_history"] = history
    payload.pop("quality_hold_reason", None)
    payload["quality_hold_resolved_at"] = resolved_at
    payload["quality_hold_resolution"] = "historical hold cleared after canonical packet-quality pass"
    return True
