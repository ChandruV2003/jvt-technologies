#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
QUEUE_ROOT = ROOT / "outreach" / "queue"
APPROVED = QUEUE_ROOT / "approved"
REVIEW = QUEUE_ROOT / "review"
REPORT_ROOT = ROOT / "outreach" / "quality-reports"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EXACT_BAD_NAMES = {
    "ata cpa contact",
    "cpa accounting",
    "cpa accountant",
    "cpa el paso tx",
    "ep cpa",
    "lb cpa",
    "top mortgage broker in new york, ny",
    "online bookkeeping & payroll for small business",
    "austin, texas bookkeeping, payroll & tax services firm",
    "small businesses tax management & bookkeeping services",
    "outsourced bookkeeping and controller services",
    "wealth management",
    "charlotte nc cpa",
    "accounting firm",
    "tax advisory services",
    "property management",
    "academy of general dentistry",
    "dentist in fort myers, fl",
}

GENERIC_PATTERNS = [
    re.compile(r"^cpa\b", re.I),
    re.compile(r"^accounting firm$", re.I),
    re.compile(r"^property management$", re.I),
    re.compile(r"^tax advisory services$", re.I),
    re.compile(r"\bcpa firm in\b", re.I),
    re.compile(r"\bbookkeeping .* for small business\b", re.I),
    re.compile(r"\boutsourced bookkeeping\b", re.I),
    re.compile(r"\baccounting payroll tax\b", re.I),
    re.compile(r"\bcpa accounting payroll tax\b", re.I),
    re.compile(r"\bmortgage broker in\b", re.I),
    re.compile(r"\b(?:dentist|doctor|chiropractor|plumber|plumbing|hvac|electrician|mortgage broker|lawyer|attorney|clinic|accountant|cpa)\s+in\b", re.I),
    re.compile(r"\b(?:top|best|top-rated|near me)\b", re.I),
    re.compile(r"\bservices?\s+in\s+[a-z ,]+$", re.I),
    re.compile(r"\b[a-z]+,?\s+[a-z]+ bookkeeping\b", re.I),
    re.compile(r"\bcontact\b", re.I),
    re.compile(r"\s[-|–—]\s*$", re.I),
]

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
    "lawrenceville",
    "management",
    "office",
    "property",
    "roofing",
    "services",
    "the",
}

HEALTH_NAME_TERMS = ("health", "chiro", "chiropractic", "dental", "dentistry", "clinic", "medical")

OFF_TARGET_NAME_TERMS = (
    "outsourcing",
    "outsourced",
    "business process outsourcing",
    " bpo ",
    "bpo company",
)

WEIRD_CPA_NAME_RE = re.compile(r"^[A-Z][A-Za-z]+ Cpa$")
SUSPICIOUS_LOCAL_PARTS = {"user", "test", "example", "noreply", "no-reply", "adminuser", "lehuser"}
RECRUITING_LOCAL_PARTS = {
    "career",
    "careers",
    "employment",
    "hr",
    "jobs",
    "recruit",
    "recruiter",
    "recruiting",
    "resumes",
    "talent",
}
RECRUITING_PATH_RE = re.compile(r"/(careers?|employment|jobs?|recruiting|talent)(?:/|$)", re.I)
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
    re.compile(r"\bjetpack workflow\b", re.I),
]
ORG_HINT_RE = re.compile(r"\b(llc|llp|pllc|pc|p\.c\.|inc|corp|company|associates|group|law|cpa|dental|dentistry|agency|management|services)\b", re.I)
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


def strip_page_title_tagline(name: str) -> str:
    candidate = re.sub(r"\s+", " ", name).strip(" -|,")
    for pattern in PAGE_TITLE_TAGLINE_PATTERNS:
        cleaned = pattern.sub("", candidate).strip(" -|,")
        if cleaned and cleaned != candidate and ORG_HINT_RE.search(cleaned):
            return cleaned
    return candidate


def has_page_title_tagline(name: str) -> bool:
    lowered = name.lower()
    if any(phrase in lowered for phrase in PAGE_TITLE_PHRASES):
        return True
    return strip_page_title_tagline(name) != re.sub(r"\s+", " ", name).strip(" -|,")


def meaningful_tokens(value: str) -> set[str]:
    raw = re.split(r"[^a-z0-9]+", value.lower())
    tokens = {token for token in raw if len(token) >= 4 and token not in DOMAIN_GENERIC_TOKENS}
    # Also split common concatenated domain stems on generic terms by removing
    # them; this catches cases like barskymanagement.com -> barsky.
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    for generic in sorted(DOMAIN_GENERIC_TOKENS, key=len, reverse=True):
        compact = compact.replace(generic, " ")
    tokens.update(token for token in compact.split() if len(token) >= 4 and token not in DOMAIN_GENERIC_TOKENS)
    return tokens


def has_name_domain_overlap(name: str, host: str) -> bool:
    host_root = root_domain(host).split(".", 1)[0]
    name_tokens = meaningful_tokens(name)
    host_tokens = meaningful_tokens(host_root)
    if not name_tokens or not host_tokens:
        return False
    host_compact = re.sub(r"[^a-z0-9]+", "", host_root.lower())
    name_compact = re.sub(r"[^a-z0-9]+", "", name.lower())
    return bool(name_tokens & host_tokens) or any(token in host_compact for token in name_tokens) or any(token in name_compact for token in host_tokens)


def is_recruiting_contact(email_local_part: str, contact_page: str) -> bool:
    local = email_local_part.lower().strip()
    if local in RECRUITING_LOCAL_PARTS:
        return True
    if any(token in local for token in ("career", "recruit", "resume")):
        return True
    parsed = urllib.parse.urlparse(contact_page if "://" in contact_page else f"https://{contact_page}") if contact_page else None
    return bool(parsed and RECRUITING_PATH_RE.search(parsed.path or ""))


def packet_paths(stem: str, source: Path) -> list[Path]:
    return sorted(source.glob(f"{stem}.*"))


def move_packet(stem: str, reason: str) -> None:
    REVIEW.mkdir(parents=True, exist_ok=True)
    for path in packet_paths(stem, APPROVED):
        if path.suffix == ".json":
            data = json.loads(path.read_text())
            data["status"] = "review"
            data["quality_hold_reason"] = reason
            for key, suffix in {"review_path": ".md", "text_path": ".txt", "html_path": ".html"}.items():
                if key in data:
                    data[key] = str(REVIEW / f"{stem}{suffix}")
            path.write_text(json.dumps(data, indent=2) + "\n")
        elif path.suffix == ".md":
            content = re.sub(r"^status:\s+\w+\s*$", "status: review", path.read_text(), flags=re.MULTILINE)
            path.write_text(content)
        path.rename(REVIEW / path.name)


def classify(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    stem = path.stem
    name = str(data.get("company_name") or "").strip()
    email = str(data.get("recipient_email") or data.get("public_email") or "").strip()
    contact_page = str(data.get("contact_page") or data.get("website") or "").strip()
    industry = str(data.get("industry") or "").strip()
    practice = str(data.get("practice_area") or "").strip()
    notes = str(data.get("notes") or "").strip()
    offer = str(data.get("personalized_offer") or "").strip()
    quality_hold_reason = str(data.get("quality_hold_reason") or "").strip()
    manual_verified = bool(data.get("manual_verified_public_contact_at") and data.get("manual_verified_source_urls"))
    lower_name = name.lower()
    cleaned_name = strip_page_title_tagline(name)
    reasons: list[str] = []
    score = 100

    if quality_hold_reason and not manual_verified:
        reasons.append(f"existing quality hold: {quality_hold_reason}")
        score -= 80
    if not name:
        reasons.append("missing company name")
        score -= 100
    if lower_name in EXACT_BAD_NAMES and not manual_verified:
        reasons.append("generic/page-title company name")
        score -= 70
    if has_page_title_tagline(name) and not manual_verified:
        reasons.append("company name includes likely page-title/tagline text")
        score -= 70
    if any(pattern.search(name) for pattern in GENERIC_PATTERNS) and not manual_verified:
        reasons.append("generic company-name pattern")
        score -= 40
    if any(term in f" {lower_name} " for term in OFF_TARGET_NAME_TERMS):
        reasons.append("off-target outsourcing/BPO company category")
        score -= 80
    if WEIRD_CPA_NAME_RE.match(name):
        reasons.append("likely unnormalized CPA name")
        score -= 35
    if not EMAIL_RE.match(email):
        reasons.append("invalid recipient email")
        score -= 100
    else:
        local, domain = email.rsplit("@", 1)
        if local.lower() in SUSPICIOUS_LOCAL_PARTS or local.lower().endswith("user"):
            reasons.append("suspicious email local part")
            score -= 60
        if is_recruiting_contact(local, contact_page):
            reasons.append("recruiting/careers contact, not business operations inbox")
            score -= 70
        host = host_from_url(contact_page)
        if host and root_domain(host) != root_domain(domain) and not manual_verified:
            reasons.append("email domain does not match contact page domain")
            score -= 60
        elif host and not has_name_domain_overlap(cleaned_name, host) and not manual_verified:
            reasons.append("company name does not clearly match contact domain")
            score -= 45
    if industry and industry not in TARGET_INDUSTRIES:
        reasons.append(f"off-target industry: {industry}")
        score -= 35
    if industry == "Property Management" and any(term in lower_name for term in HEALTH_NAME_TERMS) and not manual_verified:
        reasons.append("company name looks health/dental-related but industry is property management")
        score -= 55
    offer_lower = offer.lower()
    if "dental voice intake" in offer_lower and industry != "Dental / Healthcare Admin" and not manual_verified:
        reasons.append("offer copy is dental-specific but target industry is not dental/healthcare")
        score -= 70
    if any(term in offer_lower for term in ("medical advice", "confirming appointments", "patient")) and industry != "Dental / Healthcare Admin" and not manual_verified:
        reasons.append("offer copy uses healthcare appointment/medical language outside the healthcare lane")
        score -= 70
    if "election-sensitive" in offer_lower and industry not in {"IT / Ballot Services", "Property Management"} and not manual_verified:
        reasons.append("offer copy references ballot/election workflow outside the ballot/property lane")
        score -= 70
    target_context = "\n".join([name, industry, practice, contact_page, notes])
    if any(pattern.search(target_context) for pattern in SOFTWARE_PLATFORM_PATTERNS):
        reasons.append("software/SaaS platform target, not a service buyer")
        score -= 80
    if "Logistics / Transportation" in practice and "Law Firm" not in industry:
        score -= 10

    decision = "sendable" if score >= 70 and not any(reason.startswith(("invalid", "missing")) for reason in reasons) else "hold"
    return {
        "stem": stem,
        "decision": decision,
        "score": score,
        "reasons": reasons,
        "company_name": name,
        "recipient_email": email,
        "industry": industry,
        "practice_area": practice,
        "contact_page": contact_page,
        "generated_at": data.get("generated_at"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--move-held", action="store_true")
    parser.add_argument("--limit-sendable", type=int, default=0)
    args = parser.parse_args()

    results = [classify(path) for path in sorted(APPROVED.glob("*.json"), key=lambda item: item.stat().st_mtime)]
    sendable = [item for item in results if item["decision"] == "sendable"]
    held = [item for item in results if item["decision"] != "sendable"]
    if args.limit_sendable:
        sendable = sendable[: args.limit_sendable]

    if args.move_held:
        for item in held:
            move_packet(str(item["stem"]), "; ".join(item["reasons"]) or "quality hold")

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "approved_count_seen": len(results),
        "sendable_count": len(sendable),
        "held_count": len(held),
        "sendable": sendable,
        "held": held,
        "moved_held_to_review": bool(args.move_held),
    }
    report_path = REPORT_ROOT / f"{datetime.now().date().isoformat()}-approved-quality-gate.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report_path": str(report_path), **{k: report[k] for k in ["approved_count_seen", "sendable_count", "held_count", "moved_held_to_review"]}, "sendable_stems": [x["stem"] for x in sendable]}, indent=2))


if __name__ == "__main__":
    main()
