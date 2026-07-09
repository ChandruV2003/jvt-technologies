#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_MODEL_SCREEN_PROFILES = "strong,reviewer"

LANE_QUERIES = {
    "legal": [
        "elder law estate planning firm info@",
        "estate planning probate law firm contact email",
        "business law boutique outside general counsel contact email",
        "employment law boutique employer counsel public email",
        "elder law special needs planning contact email",
        "small business law firm contracts counsel contact email",
        "trusts estates elder law firm info@",
        "labor employment law firm HR compliance contact email",
        "corporate counsel boutique small business contact email",
        "private client estate planning law firm public email",
        "elder law firm \"info@\" \"New Jersey\"",
        "elder law firm \"info@\" \"Pennsylvania\"",
        "elder law attorney \"info@\" \"Ohio\"",
        "estate planning attorney \"info@\" \"Massachusetts\"",
        "estate planning law firm \"info@\" \"Connecticut\"",
        "probate estate planning law firm \"info@\" \"North Carolina\"",
        "special needs planning attorney \"info@\" \"California\"",
        "medicaid planning lawyer \"info@\" \"Florida\"",
        "business law firm \"info@\" \"Raleigh\"",
        "small business attorney \"info@\" \"Colorado\"",
        "outside general counsel law firm \"info@\"",
        "contract lawyer business law firm \"info@\"",
        "employment law boutique \"info@\" \"New York\"",
        "HR compliance employment law firm \"info@\"",
    ],
    "accounting": [
        "cpa firm tax advisory contact email",
        "accounting firm bookkeeping client advisory services public email",
        "tax planning and bookkeeping firm contact email",
        "small business accounting firm outsourced accounting public email",
        "cpa tax preparation payroll firm contact email",
        "client accounting services firm public email",
        "CPA firm \"info@\" \"New Jersey\"",
        "CPA tax advisory \"info@\" \"Pennsylvania\"",
        "bookkeeping firm \"info@\" \"New York\"",
        "client accounting services \"info@\" \"Massachusetts\"",
        "outsourced accounting firm \"info@\"",
        "small business CPA firm \"info@\"",
        "tax planning CPA firm \"contact@\"",
        "payroll bookkeeping accounting firm \"info@\"",
        "small business CPA firm Denver contact",
        "small business CPA firm Atlanta contact",
        "small business CPA firm Charlotte contact",
        "small business CPA firm Raleigh contact",
        "small business CPA firm Austin contact",
        "small business CPA firm Tampa contact",
        "small business CPA firm Phoenix contact",
        "small business CPA firm Philadelphia contact",
        "small business CPA firm Boston contact",
        "small business CPA firm Hartford contact",
        "bookkeeping firm Denver small business contact",
        "bookkeeping firm Atlanta small business contact",
        "bookkeeping firm Charlotte small business contact",
        "bookkeeping firm Raleigh small business contact",
        "bookkeeping firm Austin small business contact",
        "outsourced accounting firm Denver contact",
        "outsourced accounting firm Atlanta contact",
        "outsourced accounting firm Charlotte contact",
        "client accounting services CPA Denver contact",
        "client accounting services CPA Atlanta contact",
        "tax advisory CPA firm Denver contact",
        "tax advisory CPA firm Atlanta contact",
        "tax planning CPA firm Charlotte contact",
        "payroll bookkeeping CPA firm Denver contact",
    ],
    "insurance": [
        "independent insurance agency certificates of insurance \"info@\"",
        "commercial insurance agency claims support contact email",
        "business insurance agency policy documents \"info@\"",
        "insurance agency \"info@\" \"New Jersey\"",
        "insurance agency \"contact@\" \"Pennsylvania\"",
        "commercial insurance broker \"info@\"",
        "independent insurance agency \"claims\" \"info@\"",
        "employee benefits insurance agency \"contact@\"",
        "risk management insurance agency \"info@\"",
        "local insurance agency commercial lines contact email",
    ],
    "property": [
        "property management company leases maintenance requests \"info@\"",
        "residential property management company contact email",
        "HOA property management company \"info@\"",
        "property management company \"info@\" \"New Jersey\"",
        "property management company \"contact@\" \"Pennsylvania\"",
        "commercial property management company tenant portal contact",
        "real estate management company leases documents \"info@\"",
        "association management company \"info@\"",
        "rental property management company public email",
        "condominium management company contact email",
    ],
    "mortgage_title": [
        "title company closing documents \"info@\"",
        "title agency escrow closing services contact email",
        "mortgage broker loan documents \"info@\"",
        "mortgage broker \"contact@\" \"New Jersey\"",
        "title company \"info@\" \"Pennsylvania\"",
        "settlement services title agency public email",
        "real estate closing title agency contact email",
        "mortgage lender document processing contact email",
        "escrow services title company \"info@\"",
        "loan officer mortgage broker public email",
    ],
    "staffing": [
        "staffing agency onboarding documents \"info@\"",
        "recruiting firm candidate intake forms contact email",
        "temporary staffing agency \"info@\" \"New Jersey\"",
        "employment agency onboarding paperwork public email",
        "staffing firm payroll onboarding contact email",
        "recruitment agency resume screening \"contact@\"",
        "healthcare staffing agency credentialing documents \"info@\"",
        "IT staffing firm candidate submissions contact email",
        "professional staffing agency \"info@\"",
        "talent acquisition firm document workflow contact email",
    ],
    "logistics": [
        "logistics company proof of delivery invoices \"info@\"",
        "freight broker bill of lading document processing contact email",
        "3PL logistics company \"info@\"",
        "trucking company dispatch invoices paperwork contact email",
        "transportation logistics company \"contact@\" \"New Jersey\"",
        "freight forwarding company shipping documents \"info@\"",
        "warehouse logistics company receiving documents contact",
        "last mile delivery company operations contact email",
        "supply chain logistics company \"info@\"",
        "courier company proof of delivery public email",
    ],
    "construction": [
        "construction company bid documents subcontractor paperwork \"info@\"",
        "general contractor project documents contact email",
        "construction management company RFIs submittals \"info@\"",
        "commercial contractor \"info@\" \"New Jersey\"",
        "specialty contractor compliance documents contact email",
        "contractor back office paperwork public email",
        "construction accounting project controls contact email",
        "engineering construction firm document control \"info@\"",
        "renovation contractor estimates invoices contact email",
        "building contractor permit documents \"contact@\"",
    ],
    "dental_voice": [
        "dental office new patient forms appointment scheduling \"info@\"",
        "dental practice insurance verification appointment requests \"contact@\"",
        "family dental office after hours voicemail \"info@\"",
        "orthodontic practice new patient consultation \"contact@\"",
        "pediatric dental office appointment scheduling public email",
        "oral surgery practice referral intake \"info@\"",
        "dental office \"new patient\" \"insurance\" \"info@\"",
        "dentist office \"appointment\" \"contact@\" \"New Jersey\"",
        "dental practice \"forms\" \"info@\" \"Pennsylvania\"",
        "cosmetic dentistry practice consultation request email",
    ],
    "it_ballot": [
        "HOA election services ballot inspector contact email",
        "condominium board election services \"info@\"",
        "community association election services public email",
        "HOA annual meeting election ballot service contact",
        "inspector of election HOA ballot services email",
        "condo association voting services \"contact@\"",
        "board meeting AV support election services contact email",
        "HOA management election vendor ballot processing \"info@\"",
        "association voting platform services contact email",
        "third party election services condominium association",
    ],
    "local_receptionist": [
        "home services company missed calls appointment requests \"info@\"",
        "HVAC contractor emergency service calls \"contact@\"",
        "plumbing company appointment requests after hours \"info@\"",
        "roofing contractor estimate requests public email",
        "veterinary clinic appointment requests \"info@\"",
        "med spa consultation requests \"contact@\"",
        "chiropractic clinic new patient appointment \"info@\"",
        "physical therapy clinic appointment requests public email",
        "property manager maintenance calls public email",
        "title agency closing status calls \"info@\"",
    ],
}

LANE_EXPECTED_INDUSTRIES = {
    "legal": {"Law Firm"},
    "accounting": {"Accounting / Tax Firm"},
    "insurance": {"Insurance Agency"},
    "property": {"Property Management"},
    "mortgage_title": {"Mortgage / Title Services"},
    "staffing": {"Staffing / Recruiting"},
    "logistics": {"Logistics / Transportation"},
    "construction": {"Construction / Contracting"},
    "dental_voice": {"Dental / Healthcare Admin"},
    "it_ballot": {"IT / Ballot Services", "Property Management"},
    "local_receptionist": {
        "Dental / Healthcare Admin",
        "Construction / Contracting",
        "Property Management",
        "Mortgage / Title Services",
        "Home Services",
    },
}

TARGET_SEGMENTS = {
    "Elder Law": {
        "industry": "Law Firm",
        "keywords": [
        "elder law",
        "long-term care",
        "medicaid planning",
        "special needs",
        "life care planning",
        "medi-cal",
        ],
        "weight": 8,
    },
    "Estate Planning": {
        "industry": "Law Firm",
        "keywords": [
        "estate planning",
        "asset protection",
        "wills",
        "trusts",
        "probate",
        "estate administration",
        "legacy planning",
        ],
        "weight": 7,
    },
    "Business Law": {
        "industry": "Law Firm",
        "keywords": [
        "business law",
        "corporate law",
        "outside general counsel",
        "general counsel",
        "commercial law",
        "business transactions",
        "small business",
        "contracts",
        "corporate counsel",
        ],
        "weight": 6,
    },
    "Employment Law": {
        "industry": "Law Firm",
        "keywords": [
        "employment law",
        "labor law",
        "hr compliance",
        "workplace disputes",
        "employee handbook",
        "wage and hour",
        ],
        "weight": 6,
    },
    "Tax & Accounting": {
        "industry": "Accounting / Tax Firm",
        "keywords": [
            "cpa",
            "certified public accountant",
            "accounting",
            "accountant",
            "tax planning",
            "tax preparation",
            "tax prep",
            "tax advisory",
            "tax services",
            "irs representation",
        ],
        "weight": 7,
    },
    "Bookkeeping / CAS": {
        "industry": "Accounting / Tax Firm",
        "keywords": [
            "bookkeeping",
            "bookkeeper",
            "client accounting services",
            "cas",
            "outsourced accounting",
            "controller services",
            "monthly close",
            "payroll",
        ],
        "weight": 6,
    },
    "Commercial Insurance": {
        "industry": "Insurance Agency",
        "keywords": [
            "commercial insurance",
            "business insurance",
            "certificate of insurance",
            "certificates of insurance",
            "claims",
            "policy",
            "policies",
            "risk management",
            "employee benefits",
            "insurance agency",
            "insurance broker",
        ],
        "weight": 7,
    },
    "Property Management": {
        "industry": "Property Management",
        "keywords": [
            "property management",
            "tenant",
            "tenants",
            "lease",
            "leases",
            "maintenance request",
            "hoa",
            "condominium",
            "association management",
            "rent collection",
            "rental property",
        ],
        "weight": 7,
    },
    "Mortgage / Title": {
        "industry": "Mortgage / Title Services",
        "keywords": [
            "mortgage",
            "loan documents",
            "loan officer",
            "title company",
            "title agency",
            "escrow",
            "settlement services",
            "closing documents",
            "real estate closing",
            "lender",
        ],
        "weight": 7,
    },
    "Staffing / Recruiting": {
        "industry": "Staffing / Recruiting",
        "keywords": [
            "staffing",
            "recruiting",
            "recruitment",
            "candidate",
            "resume",
            "onboarding",
            "employment agency",
            "temporary staffing",
            "credentialing",
            "talent acquisition",
        ],
        "weight": 7,
    },
    "Logistics / Transportation": {
        "industry": "Logistics / Transportation",
        "keywords": [
            "logistics",
            "freight",
            "bill of lading",
            "proof of delivery",
            "transportation",
            "trucking",
            "dispatch",
            "warehouse",
            "shipping documents",
            "courier",
            "3pl",
        ],
        "weight": 7,
    },
    "Construction Admin": {
        "industry": "Construction / Contracting",
        "keywords": [
            "construction",
            "general contractor",
            "contractor",
            "subcontractor",
            "submittals",
            "rfi",
            "rfis",
            "bid documents",
            "permit",
            "estimates",
            "project documents",
        ],
        "weight": 6,
    },
    "Dental Voice Intake": {
        "industry": "Dental / Healthcare Admin",
        "keywords": [
            "dental",
            "dentist",
            "orthodontic",
            "oral surgery",
            "new patient",
            "patient forms",
            "appointment",
            "appointments",
            "insurance verification",
            "consultation",
            "after hours",
        ],
        "weight": 8,
    },
    "HOA / Ballot Workflow": {
        "industry": "IT / Ballot Services",
        "keywords": [
            "hoa election",
            "condominium election",
            "community association",
            "board meeting",
            "ballot",
            "ballots",
            "voting",
            "election services",
            "inspector of election",
            "annual meeting",
            "association election",
        ],
        "weight": 8,
    },
    "Local Receptionist Intake": {
        "industry": "Home Services",
        "keywords": [
            "missed calls",
            "appointment requests",
            "service calls",
            "estimate request",
            "consultation request",
            "after hours",
            "emergency service",
            "new patient",
            "maintenance calls",
            "callback",
        ],
        "weight": 7,
    },
}

NEGATIVE_TERMS = [
    "personal injury",
    "criminal defense",
    "bankruptcy",
    "immigration",
    "family law",
    "software platform",
    "management software",
    "saas",
    "resume writing",
]

IGNORE_HOSTS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "x.com",
    "twitter.com",
    "yelp.com",
    "avvo.com",
    "justia.com",
    "martindale.com",
    "superlawyers.com",
    "findlaw.com",
    "lawyers.com",
    "mapquest.com",
    "stackoverflow.com",
    "stackexchange.com",
    "reddit.com",
    "forbes.com",
    "coursera.org",
    "trustpilot.com",
    "expertise.com",
    "merriam-webster.com",
}
BLOCKED_EARLY_OUTREACH_HOSTS = {
    "skadden.com",
    "kirkland.com",
    "lw.com",
    "cravath.com",
    "wlrk.com",
    "sullcrom.com",
    "davispolk.com",
    "stblaw.com",
    "paulweiss.com",
    "whitecase.com",
    "freshfields.com",
    "morganlewis.com",
    "gtlaw.com",
    "deloitte.com",
    "pwc.com",
    "ey.com",
    "kpmg.com",
}
BLOCKED_EARLY_OUTREACH_NAMES = (
    "skadden",
    "kirkland",
    "latham",
    "cravath",
    "wachtell",
    "sullivan & cromwell",
    "sullivan cromwell",
    "davis polk",
    "simpson thacher",
    "paul weiss",
    "white & case",
    "freshfields",
    "morgan lewis",
    "greenberg traurig",
    "deloitte",
    "pricewaterhousecoopers",
    "pwc",
    "ernst & young",
    "ey",
    "kpmg",
    "express employment",
)

STATE_CODES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|IA|ID|IL|IN|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|"
    "NC|ND|NE|NH|NJ|NM|NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY|DC"
)
CITY_STATE_RE = re.compile(rf"\b([A-Z][A-Za-z .'-]+,\s(?:{STATE_CODES}))\b")
CITY_STATE_EXACT_RE = re.compile(rf"^[A-Z][A-Za-z .'-]+,\s(?:{STATE_CODES})$")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
META_SITE_NAME_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:site_name|application-name)["\'][^>]+content=["\']([^"\']+)',
    re.I,
)
JSONLD_NAME_RE = re.compile(
    r'"@type"\s*:\s*"(?:Organization|LegalService|Attorney)"[^}]{0,1200}?"name"\s*:\s*"([^"]+)"',
    re.I | re.S,
)
A_TAG_RE = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
TEXT_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
DDG_RESULT_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)</div>',
    re.I | re.S,
)
MARKDOWN_LINK_RE = re.compile(r"(?:^|\n)(?:#+\s*)?\[([^\]]{4,180})\]\((https?://[^)\s]+)\)")
BING_RESULT_RE = re.compile(r"<h2[^>]*>\s*<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
YAHOO_RESULT_BLOCK_RE = re.compile(r"<li[^>]*>\s*<div[^>]+class=[\"'][^\"']*\balgo\b[^\"']*.*?</li>", re.I | re.S)
GENERIC_TITLES = {
    "home",
    "about",
    "contact",
    "welcome",
    "homepage",
    "home page",
    "our firm",
    "property management",
    "academy of general dentistry",
}
BAD_PREFIXES = (
    "contact ",
    "elder law",
    "estate planning",
    "probate",
    "wills",
    "trusts",
    "employment law",
    "business law",
    "labor law",
    "home page",
)
GENERIC_PRACTICE_PHRASES = (
    "law firm",
    "law office",
    "law offices",
    "elder law firm",
    "elder law attorneys",
    "elder law attorney",
    "estate probate lawyer",
    "estate planning attorneys",
    "new jersey elder law",
    "certified elder law attorney",
    "cpa websites",
    "new jersey employment lawyer",
    "new jersey employment lawyers",
    "private client law firm",
    "nyc law firm",
    "accounting firm",
    "cpa firm",
    "cpa & accountant",
    "bookkeeping firm",
    "bookkeeping services in",
    "property management",
    "academy of general dentistry",
)
PAGE_TITLE_TAGLINE_PATTERNS = (
    re.compile(r"\.\s+(?:one|a|the|your|our)\b.+$", re.I),
    re.compile(r":\s+(?:global|expert|trusted|maximize|online|outsourced)\b.+$", re.I),
    re.compile(r"\s+-\s+(?:one|a|the|your|our|expert|trusted|maximize|online|outsourced)\b.+$", re.I),
)
GENERIC_NAME_WORDS = {
    "a",
    "an",
    "and",
    "asset",
    "assets",
    "agency",
    "attorney",
    "attorneys",
    "broker",
    "care",
    "certified",
    "client",
    "commercial",
    "company",
    "dental",
    "dentistry",
    "elder",
    "employment",
    "estate",
    "firm",
    "group",
    "home",
    "homepage",
    "jersey",
    "law",
    "lawyer",
    "lawyers",
    "lancaster",
    "management",
    "manager",
    "managers",
    "medicaid",
    "new",
    "north",
    "nj",
    "nyc",
    "office",
    "offices",
    "of",
    "p",
    "pa",
    "pc",
    "cpa",
    "planning",
    "pllc",
    "probate",
    "protection",
    "property",
    "private",
    "services",
    "south",
    "special",
    "the",
    "touch",
    "trusts",
    "w",
    "wills",
}
DOMAIN_GENERIC_TOKENS = GENERIC_NAME_WORDS | {
    "admin",
    "associates",
    "center",
    "centers",
    "consulting",
    "corp",
    "corporation",
    "dmd",
    "doctor",
    "dr",
    "inc",
    "ltd",
    "online",
    "professional",
    "usa",
}
ORG_HINTS = (
    "agency",
    "advisors",
    "advisory",
    "associates",
    "broker",
    "company",
    "contractor",
    "cpa",
    "clinic",
    "dental",
    "dentist",
    "escrow",
    "election",
    "firm",
    "group",
    "health",
    "healthcare",
    "insurance",
    "logistics",
    "management",
    "mortgage",
    "office",
    "offices",
    "orthodontic",
    "partners",
    "plumbing",
    "property",
    "properties",
    "recruiting",
    "roofing",
    "staffing",
    "services",
    "solutions",
    "title",
    "transport",
    "transportation",
    "llp",
    "pllc",
    "llc",
    "p.a.",
    "pa",
    "p.c.",
    "pc",
    "esq",
)


def strip_tags(value: str) -> str:
    return WHITESPACE_RE.sub(" ", unescape(TEXT_TAG_RE.sub(" ", value))).strip()


def fetch_text(url: str, timeout: int = 8) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
    return payload.decode("utf-8", errors="ignore")


def fetch_html(url: str) -> str:
    try:
        return fetch_text(url)
    except Exception:
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            jina_url = f"https://r.jina.ai/http://{parsed.netloc}{parsed.path or '/'}"
            if parsed.query:
                jina_url += f"?{parsed.query}"
            try:
                return fetch_text(jina_url)
            except Exception:
                return ""
        return ""


def parse_search_results(html: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for href, title_html, tail in DDG_RESULT_RE.findall(html):
        href = href.strip()
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            qs = parse_qs(parsed.query)
            href = qs.get("uddg", [href])[0]
        title = strip_tags(title_html)
        snippet = strip_tags(tail)[:280]
        if href.startswith("//"):
            href = f"https:{href}"
        if href.startswith("/"):
            href = f"https://html.duckduckgo.com{href}"
        results.append({"url": href, "title": title, "snippet": snippet})
    return results


def unwrap_bing_url(url: str) -> str:
    parsed = urlparse(url)
    if "bing.com" not in parsed.netloc or not parsed.path.startswith("/ck/"):
        return url
    value = parse_qs(parsed.query).get("u", [""])[0]
    if not value:
        return url
    # Bing wraps outbound URLs as "a1" + urlsafe-base64(target).
    encoded = value[2:] if value.startswith("a1") else value
    padded = encoded + ("=" * (-len(encoded) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
    except Exception:
        return url
    return decoded if decoded.startswith(("http://", "https://")) else url


def unwrap_yahoo_url(url: str) -> str:
    parsed = urlparse(url)
    if "search.yahoo.com" not in parsed.netloc:
        return url
    match = re.search(r"/RU=([^/]+)/RK=", url)
    if not match:
        return url
    target = unquote(match.group(1))
    return target if target.startswith(("http://", "https://")) else url


def parse_bing_results(html: str, limit: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in BING_RESULT_RE.finditer(html):
        href = unwrap_bing_url(unescape(match.group(1)).strip())
        title = strip_tags(match.group(2))
        parsed = urlparse(href)
        host = parsed.netloc.lower().removeprefix("www.")
        if not title or not host or host in seen:
            continue
        if any(blocked in host for blocked in ("bing.com", "microsoft.com", "google.com")):
            continue
        snippet = strip_tags(html[match.end() : match.end() + 900])[:280]
        results.append({"url": href, "title": title, "snippet": snippet})
        seen.add(host)
        if len(results) >= limit:
            break
    return results


def parse_yahoo_results(html: str, limit: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for block_match in YAHOO_RESULT_BLOCK_RE.finditer(html):
        block = block_match.group(0)
        href_match = re.search(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>.*?<h3[^>]*class=[\"'][^\"']*\btitle\b[^\"']*[\"'][^>]*>(.*?)</h3>", block, re.I | re.S)
        if not href_match:
            continue
        href = unwrap_yahoo_url(unescape(href_match.group(1)).strip())
        title = strip_tags(href_match.group(2))
        parsed = urlparse(href)
        host = parsed.netloc.lower().removeprefix("www.")
        if not title or not host or host in seen:
            continue
        if any(blocked in host for blocked in ("yahoo.com", "bing.com", "microsoft.com", "google.com")):
            continue
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.I | re.S)
        snippet = strip_tags(snippet_match.group(1))[:280] if snippet_match else ""
        results.append({"url": href, "title": title, "snippet": snippet})
        seen.add(host)
        if len(results) >= limit:
            break
    return results


def parse_markdown_search_results(text: str, limit: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in MARKDOWN_LINK_RE.finditer(text):
        title = strip_tags(match.group(1))
        href = unwrap_bing_url(match.group(2).strip())
        parsed = urlparse(href)
        host = parsed.netloc.lower().removeprefix("www.")
        if not host or host in seen:
            continue
        if any(blocked in host for blocked in ("bing.com", "microsoft.com", "google.com")):
            continue
        if parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
            continue
        snippet_start = match.end()
        snippet = strip_tags(text[snippet_start : snippet_start + 700])[:280]
        results.append({"url": href, "title": title, "snippet": snippet})
        seen.add(host)
        if len(results) >= limit:
            break
    return results


def normalize_homepage(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    host = parsed.netloc.lower().removeprefix("www.")
    if host in IGNORE_HOSTS or host in BLOCKED_EARLY_OUTREACH_HOSTS or host.endswith(".pdf"):
        return None
    return f"https://{host}/"


def domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def root_domain(host: str) -> str:
    clean = host.lower().removeprefix("www.").split(":", 1)[0]
    parts = [part for part in clean.split(".") if part]
    if len(parts) < 2:
        return clean
    return ".".join(parts[-2:])


def email_matches_host(public_email: str, host: str) -> bool:
    if "@" not in public_email or not host:
        return False
    email_domain = public_email.rsplit("@", 1)[1].lower()
    return root_domain(email_domain) == root_domain(host)


def extract_title(html: str) -> str:
    match = TITLE_RE.search(html)
    if not match:
        return ""
    title = strip_tags(match.group(1))
    for delim in (" | ", " - ", " — ", " :: "):
        if delim in title:
            title = title.split(delim, 1)[0].strip()
            break
    return title


def extract_meta_site_names(html: str) -> list[str]:
    return [strip_tags(match) for match in META_SITE_NAME_RE.findall(html)]


def extract_jsonld_names(html: str) -> list[str]:
    return [strip_tags(match) for match in JSONLD_NAME_RE.findall(html)]


def host_name(host: str) -> str:
    root = host.split(".", 1)[0]
    cleaned = root.replace("-", " ").replace("_", " ").strip()
    if cleaned.lower().endswith("cpa") and not cleaned.lower().endswith(" cpa"):
        cleaned = f"{cleaned[:-3].strip()} CPA"
    return cleaned.title()


def meaningful_tokens(value: str, generic_tokens: set[str] | None = None) -> set[str]:
    generic = generic_tokens or GENERIC_NAME_WORDS
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) >= 3 and token not in generic
    }


def domain_name_tokens(host: str) -> set[str]:
    root = host.split(".", 1)[0]
    return meaningful_tokens(root.replace("-", " ").replace("_", " "), DOMAIN_GENERIC_TOKENS)


def has_name_domain_overlap(company_name: str, host: str, public_email: str = "") -> bool:
    name_tokens = meaningful_tokens(company_name)
    host_tokens = domain_name_tokens(host)
    email_host = public_email.rsplit("@", 1)[-1] if "@" in public_email else ""
    email_tokens = domain_name_tokens(email_host) if email_host else set()
    comparison_tokens = host_tokens | email_tokens
    if not name_tokens or not comparison_tokens:
        return False
    if name_tokens & comparison_tokens:
        return True
    compact_domains = [
        re.sub(r"[^a-z0-9]+", "", host.split(".", 1)[0].lower()),
    ]
    if email_host:
        compact_domains.append(re.sub(r"[^a-z0-9]+", "", email_host.split(".", 1)[0].lower()))
    return any(token in compact for token in name_tokens for compact in compact_domains)


def strip_page_title_tagline(name: str) -> str:
    candidate = WHITESPACE_RE.sub(" ", name).strip(" -|,")
    for pattern in PAGE_TITLE_TAGLINE_PATTERNS:
        cleaned = pattern.sub("", candidate).strip(" -|,")
        if cleaned and cleaned != candidate and any(hint in cleaned.lower() for hint in ORG_HINTS):
            return cleaned
    return candidate


def looks_like_company_name(name: str) -> bool:
    candidate = strip_page_title_tagline(name)
    lowered = candidate.lower()
    if not candidate or len(candidate) < 5:
        return False
    if candidate.startswith("@"):
        return False
    if "|" in candidate:
        return False
    if len(candidate) > 80 and any(
        term in lowered
        for term in (
            "enrolled agent",
            "certified acceptance",
            "bookkeeper",
            "accountant",
            "tax prep",
            "audit expert",
            "business consultant",
        )
    ):
        return False
    if "www." in lowered or ".com" in lowered or "http://" in lowered or "https://" in lowered:
        return False
    if any(ch.isdigit() for ch in lowered):
        return False
    if " " not in candidate and "." not in candidate and "&" not in candidate:
        return False
    if lowered in GENERIC_TITLES:
        return False
    if lowered.startswith("about "):
        return False
    if lowered in {
        "cpa mba",
        "professional staffing agency",
        "temporary employment services & staffing agency",
        "property management",
        "academy of general dentistry",
        "global business process outsourcing bpo company",
    }:
        return False
    if any(
        phrase in lowered
        for phrase in (
            "one law firm, diverse solutions",
            "expert tax services at your fingertips",
            "global business process outsourcing",
            "online bookkeeping & payroll",
            "accounting payroll tax business services",
            "cpa accounting payroll tax",
            "outsourced accounting",
            "outsourced bookkeeping",
        )
    ):
        return False
    if lowered.startswith("jobs and staffing solutions"):
        return False
    if lowered.startswith("title company "):
        return False
    if " company in " in lowered or " agency in " in lowered:
        return False
    if re.search(r"^cpa\s+firm\s+[a-z .'-]+$", lowered):
        return False
    if re.search(r"^[a-z .'-]+\s+cpa\s+firm$", lowered):
        return False
    if lowered.startswith("trusted accounting firm for business"):
        return False
    if re.search(r"^accounting\s*&\s*consulting\s+firm\s+in\s+[a-z ,.]+$", lowered):
        return False
    if re.search(r"^[a-z ,.]+\s+(accounting|consulting|cpa)\s+firm$", lowered):
        return False
    if re.search(r"^[a-z .'-]+\s+(?:[a-z]{2}|[a-z]+)\s+cpa\s*&\s*accountant$", lowered):
        return False
    if lowered.startswith("bookkeeping services in "):
        return False
    if re.search(r"\b(company|agency|firm)\s+[a-z .'-]+\s+(?:[a-z]{2}|[a-z]+)$", lowered):
        return False
    if CITY_STATE_RE.search(candidate) and any(
        phrase in lowered
        for phrase in ("accounting firm", "cpa firm", "law firm", "property management")
    ):
        return False
    if "software" in lowered or "platform" in lowered:
        return False
    if "get in touch" in lowered or "contact us" in lowered:
        return False
    if lowered.endswith(" home page") or lowered.startswith("home page"):
        return False
    if any(lowered.startswith(prefix) for prefix in BAD_PREFIXES):
        return False
    if any(phrase in lowered for phrase in GENERIC_PRACTICE_PHRASES):
        tokens = [token for token in re.split(r"[^a-z]+", lowered) if token]
        distinct = [token for token in tokens if token not in GENERIC_NAME_WORDS]
        if not distinct:
            return False
    if "search results" in lowered:
        return False
    if any(term in lowered for term in BLOCKED_EARLY_OUTREACH_NAMES):
        return False
    if not any(hint in lowered for hint in ORG_HINTS):
        return False
    return True


def choose_company_name(*candidates: str, host: str) -> str:
    for candidate in candidates:
        candidate = strip_page_title_tagline(candidate)
        if looks_like_company_name(candidate):
            return candidate
    fallback = host_name(host)
    return fallback if looks_like_company_name(fallback) else ""


def extract_contact_link(base_url: str, html: str) -> str:
    for href, text in A_TAG_RE.findall(html):
        href = unescape(href).strip()
        text = strip_tags(text).lower()
        combined = f"{href.lower()} {text}"
        if "contact" not in combined and "about" not in combined:
            continue
        if href.startswith("mailto:"):
            continue
        return urljoin(base_url, href)
    for suffix in ("/contact", "/contact-us", "/contacts", "/about/contact"):
        return urljoin(base_url, suffix)
    return base_url


def extract_emails(text: str) -> list[str]:
    emails = []
    for email in EMAIL_RE.findall(text):
        cleaned = email.strip(".,;:()[]{}<>").lower()
        if cleaned.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            continue
        if cleaned not in emails:
            emails.append(cleaned)
    return emails


def pick_public_email(emails: Iterable[str]) -> str:
    emails = list(emails)
    if not emails:
        return ""
    preferred = [
        email
        for email in emails
        if email.startswith(("info@", "contact@", "hello@", "admin@", "office@"))
    ]
    return (preferred or emails)[0]


def detect_practice_areas(text: str) -> list[str]:
    lowered = text.lower()
    hits: list[tuple[int, str]] = []
    for practice, config in TARGET_SEGMENTS.items():
        keywords = config["keywords"]
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score:
            hits.append((score, practice))
    hits.sort(reverse=True)
    return [practice for _, practice in hits[:3]]


def infer_industry(text: str, practice_areas: list[str]) -> str:
    industry_votes: dict[str, int] = {}
    for practice_area in practice_areas:
        config = TARGET_SEGMENTS.get(practice_area)
        if not config:
            continue
        industry = str(config["industry"])
        industry_votes[industry] = industry_votes.get(industry, 0) + 2

    lowered = text.lower()
    if "law firm" in lowered or "attorney" in lowered:
        industry_votes["Law Firm"] = industry_votes.get("Law Firm", 0) + 1
    if any(keyword in lowered for keyword in ("cpa", "accounting", "accountant", "bookkeeping", "tax planning", "tax preparation", "tax prep")):
        industry_votes["Accounting / Tax Firm"] = industry_votes.get("Accounting / Tax Firm", 0) + 1
    if any(keyword in lowered for keyword in ("insurance agency", "commercial insurance", "certificate of insurance", "insurance broker")):
        industry_votes["Insurance Agency"] = industry_votes.get("Insurance Agency", 0) + 1
    if any(keyword in lowered for keyword in ("property management", "tenant", "lease", "hoa", "association management")):
        industry_votes["Property Management"] = industry_votes.get("Property Management", 0) + 1
    if any(keyword in lowered for keyword in ("title company", "title agency", "mortgage", "escrow", "closing documents")):
        industry_votes["Mortgage / Title Services"] = industry_votes.get("Mortgage / Title Services", 0) + 1
    if any(keyword in lowered for keyword in ("staffing", "recruiting", "candidate", "resume", "onboarding")):
        industry_votes["Staffing / Recruiting"] = industry_votes.get("Staffing / Recruiting", 0) + 1
    if any(keyword in lowered for keyword in ("logistics", "freight", "bill of lading", "proof of delivery", "transportation", "trucking")):
        industry_votes["Logistics / Transportation"] = industry_votes.get("Logistics / Transportation", 0) + 1
    if any(keyword in lowered for keyword in ("construction", "general contractor", "submittals", "rfi", "subcontractor", "permit")):
        industry_votes["Construction / Contracting"] = industry_votes.get("Construction / Contracting", 0) + 1
    if any(keyword in lowered for keyword in ("dental", "dentist", "orthodontic", "oral surgery", "new patient forms", "insurance verification")):
        industry_votes["Dental / Healthcare Admin"] = industry_votes.get("Dental / Healthcare Admin", 0) + 1
    if any(keyword in lowered for keyword in ("hoa election", "condominium election", "community association", "ballot", "voting", "inspector of election")):
        industry_votes["IT / Ballot Services"] = industry_votes.get("IT / Ballot Services", 0) + 1
    if any(keyword in lowered for keyword in ("hvac", "plumbing", "roofing", "home services", "service calls", "estimate request", "missed calls")):
        industry_votes["Home Services"] = industry_votes.get("Home Services", 0) + 1

    if not industry_votes:
        return ""

    return max(industry_votes.items(), key=lambda item: item[1])[0]


def score_fit(text: str, contact_page: str, public_email: str, practice_areas: list[str], industry: str) -> int:
    lowered = text.lower()
    score = 52
    if industry == "Law Firm" and ("law firm" in lowered or "attorney" in lowered):
        score += 6
    if industry == "Accounting / Tax Firm" and any(keyword in lowered for keyword in ("cpa", "accounting", "accountant", "bookkeeping", "tax planning", "tax preparation", "tax prep")):
        score += 6
    if industry not in {"Law Firm", "Accounting / Tax Firm"} and practice_areas:
        score += 5
    for practice in practice_areas:
        config = TARGET_SEGMENTS.get(practice)
        if not config:
            continue
        hits = sum(1 for keyword in config["keywords"] if keyword in lowered)
        score += min(hits * int(config["weight"]), 21)
    if contact_page:
        score += 4
    if public_email:
        score += 7
    for term in NEGATIVE_TERMS:
        if term in lowered:
            score -= 8
    return max(0, min(score, 95))


def clean_city_state(value: str) -> str:
    cleaned = WHITESPACE_RE.sub(" ", value).strip()
    if ". " in cleaned:
        cleaned = cleaned.rsplit(". ", 1)[-1].strip()
    for prefix in ("Locations in ", "Location in ", "Based in ", "Serving ", "Offices in "):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned if CITY_STATE_EXACT_RE.fullmatch(cleaned) else ""


def find_city_state(*texts: str) -> str:
    for text in texts:
        match = CITY_STATE_RE.search(text)
        if match:
            cleaned = clean_city_state(match.group(1))
            if cleaned:
                return cleaned
    return ""


def build_note(industry: str, practice_areas: list[str], public_email: str, contact_page: str, homepage: str) -> str:
    practice_text = ", ".join(practice_areas) if practice_areas else "document-heavy legal"
    industry_text = (industry or "document-heavy professional team").replace(" / ", "/").lower()
    email_text = "with public email" if public_email else "with visible contact path"
    source = contact_page or homepage
    return (
        f"Auto-researched {industry_text} focused on {practice_text.lower()} {email_text} "
        f"and strong private-workflow fit. Source: {source}"
    )


def load_existing(db_path: Path) -> tuple[set[str], set[str]]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT company_name, website FROM leads").fetchall()
    conn.close()
    names = {row[0].strip().lower() for row in rows if row[0]}
    hosts = {domain(row[1]) for row in rows if row[1]}
    return names, hosts


def load_state(state_path: Path) -> dict:
    default_state = {
        "query_offsets": {lane: 0 for lane in LANE_QUERIES},
        "seen_domains": [],
        "last_run": None,
    }
    if not state_path.exists():
        return default_state
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return default_state

    if "query_offsets" not in state:
        legacy_offset = int(state.get("query_offset", 0))
        state["query_offsets"] = {lane: 0 for lane in LANE_QUERIES}
        state["query_offsets"]["legal"] = legacy_offset % len(LANE_QUERIES["legal"])
    for lane, queries in LANE_QUERIES.items():
        state.setdefault("query_offsets", {})
        state["query_offsets"].setdefault(lane, 0)
        state["query_offsets"][lane] = int(state["query_offsets"][lane]) % len(queries)
    state.setdefault("seen_domains", [])
    state.setdefault("last_run", None)
    return state


def save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["seen_domains"] = sorted(set(state.get("seen_domains", [])))[-5000:]
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def pick_queries(state: dict, queries_per_run: int, lanes: list[str] | None = None) -> list[dict[str, str]]:
    picked: list[dict[str, str]] = []
    lane_names = lanes or list(LANE_QUERIES.keys())
    offsets = state.setdefault("query_offsets", {lane: 0 for lane in lane_names})
    for index in range(queries_per_run):
        lane = lane_names[index % len(lane_names)]
        lane_queries = LANE_QUERIES[lane]
        offset = int(offsets.get(lane, 0))
        query = lane_queries[offset % len(lane_queries)]
        offsets[lane] = (offset + 1) % len(lane_queries)
        picked.append({"lane": lane, "query": query})
    return picked


def search(query: str, results_per_query: int) -> list[dict[str, str]]:
    encoded = quote_plus(query)
    attempts = [
        (
            f"https://html.duckduckgo.com/html/?q={encoded}",
            lambda html: [] if "anomaly.js" in html else parse_search_results(html)[:results_per_query],
        ),
        (f"https://www.bing.com/search?q={encoded}", lambda html: parse_bing_results(html, results_per_query)),
        (f"https://search.yahoo.com/search?p={encoded}", lambda html: parse_yahoo_results(html, results_per_query)),
        (
            f"https://r.jina.ai/http://www.bing.com/search?q={encoded}",
            lambda text: parse_markdown_search_results(text, results_per_query),
        ),
    ]
    for url, parser in attempts:
        try:
            results = [
                result
                for result in parser(fetch_text(url))
                if normalize_homepage(result.get("url", ""))
            ][:results_per_query]
        except Exception:
            continue
        if results:
            return results
    return []


def parse_profiles(value: str) -> list[str]:
    profiles = []
    for item in value.split(","):
        profile = item.strip().lower()
        if profile in {"strong", "reviewer"} and profile not in profiles:
            profiles.append(profile)
    return profiles


def run_model_screen(root: Path, state_dir: Path, rows: list[dict[str, str]], profiles: list[str], timeout: int) -> tuple[list[dict[str, str]], list[dict]]:
    if not rows or not profiles:
        return rows, []

    screen_dir = state_dir / "model-screen"
    screen_dir.mkdir(parents=True, exist_ok=True)
    input_path = screen_dir / "latest-candidates.json"
    input_payload = [
        {
            "index": index,
            "company_name": row["company_name"],
            "website": row["website"],
            "city_state": row["city_state"],
            "industry": row["industry"],
            "practice_area": row["practice_area"],
            "public_email": row["public_email"],
            "fit_score": row["fit_score"],
            "notes": row["notes"],
        }
        for index, row in enumerate(rows)
    ]
    input_path.write_text(json.dumps(input_payload, indent=2) + "\n", encoding="utf-8")

    runs: list[dict] = []
    results_by_index: dict[int, list[dict]] = {index: [] for index in range(len(rows))}
    for profile in profiles:
        output_path = screen_dir / f"latest-{profile}.json"
        command = [
            sys.executable,
            str(root / "lead-pipeline" / "tools" / "model_screen_lead.py"),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--profile",
            profile,
            "--max-tokens",
            "1800" if profile == "reviewer" else "900",
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            run_results = payload.get("results", [])
            for result in run_results:
                index = int(result.get("index", -1))
                if index in results_by_index:
                    result["profile"] = profile
                    results_by_index[index].append(result)
            run_record = {"profile": profile, "status": "ok", "count": len(run_results), "output": str(output_path)}
            stderr_tail = (completed.stderr or "").strip().splitlines()[-5:]
            if stderr_tail:
                run_record["stderr_tail"] = stderr_tail
            if payload.get("parse_error"):
                run_record["parse_error"] = payload.get("parse_error")
            runs.append(run_record)
        except Exception as exc:
            runs.append({"profile": profile, "status": "error", "error": str(exc)[:260], "output": str(output_path)})

    accepted: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        model_results = results_by_index.get(index, [])
        if not model_results:
            row["notes"] = f"{row['notes']} Model screen unavailable; retained by deterministic filter."
            accepted.append(row)
            continue
        if not all(result.get("accept") and int(result.get("score", 0)) >= 70 for result in model_results):
            continue
        summary = "; ".join(
            f"{result['profile']} {int(result.get('score', 0))}: {result.get('reason', '').strip()}"
            for result in model_results
        )
        row["notes"] = f"{row['notes']} Model screen accepted: {summary[:700]}"
        accepted.append(row)

    latest_path = screen_dir / "latest-summary.json"
    latest_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "profiles": profiles,
                "candidate_count": len(rows),
                "accepted_count": len(accepted),
                "runs": runs,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return accepted, runs


def write_csv(csv_path: Path, rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "company_name",
        "website",
        "city_state",
        "industry",
        "practice_area",
        "contact_page",
        "public_email",
        "notes",
        "fit_score",
        "outreach_status",
        "follow_up_status",
        "last_touched_date",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def import_csv(db_path: Path, csv_path: Path, root: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(root / "lead-pipeline" / "tools" / "lead_pipeline_cli.py"),
            "import-csv",
            "--db",
            str(db_path),
            "--csv",
            str(csv_path),
        ],
        check=True,
    )


def fetch_total_leads(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    total = conn.execute("SELECT count(*) FROM leads").fetchone()[0]
    conn.close()
    return int(total)


def lookup_lead_id(db_path: Path, company_name: str, website: str) -> int | None:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT id FROM leads WHERE company_name = ? AND website = ?",
        (company_name, website),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else None


def generate_drafts(root: Path, db_path: Path, rows: list[dict[str, str]], limit: int) -> list[str]:
    created: list[str] = []
    for row in sorted(rows, key=lambda item: int(item["fit_score"]), reverse=True):
        if len(created) >= limit or int(row["fit_score"]) < 85:
            break
        lead_id = lookup_lead_id(db_path, row["company_name"], row["website"])
        if not lead_id:
            continue
        subprocess.run(
            [
                sys.executable,
                str(root / "outreach" / "tools" / "generate_draft.py"),
                "--db",
                str(db_path),
                "--lead-id",
                str(lead_id),
                "--template",
                str(root / "outreach" / "templates" / "initial-introduction.md"),
                "--output-dir",
                str(root / "outreach" / "queue" / "draft"),
                "--contact-name",
                "team",
                "--reply-to-email",
                "hello@jvt-technologies.com",
                "--site-url",
                "https://jvt-technologies.com",
                "--sender-name",
                "Chandru Vasudevan",
                "--sender-title",
                "Founder",
                "--sender-company",
                "JVT Technologies LLC",
            ],
            check=True,
        )
        created.append(row["company_name"])
    return created


def write_status(status_path: Path, *, queries: list[dict[str, str]], csv_path: Path | None, added: list[dict[str, str]], total_leads: int, drafted: list[str], model_screen_runs: list[dict]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    industry_counts: dict[str, int] = {}
    for row in added:
        industry = row.get("industry") or "unknown"
        industry_counts[industry] = industry_counts.get(industry, 0) + 1
    lines = [
        f"last_run: {datetime.now().isoformat(timespec='seconds')}",
        f"total_leads: {total_leads}",
        f"new_leads_added: {len(added)}",
        f"csv_tranche: {csv_path if csv_path else 'none'}",
        "",
        "queries:",
    ]
    lines.extend(f"- [{item['lane']}] {item['query']}" for item in queries)
    lines.extend(["", "industries_added:"])
    if industry_counts:
        lines.extend(f"- {industry}: {count}" for industry, count in sorted(industry_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "model_screen:"])
    if model_screen_runs:
        for run in model_screen_runs:
            if run.get("status") == "ok":
                lines.append(f"- {run['profile']}: ok ({run.get('count', 0)} results)")
            else:
                lines.append(f"- {run['profile']}: error ({run.get('error', 'unknown')})")
    else:
        lines.append("- not run")
    lines.extend(["", "new_leads:"])
    if added:
        lines.extend(
            f"- {row['company_name']} ({row['fit_score']})"
            for row in sorted(added, key=lambda item: int(item["fit_score"]), reverse=True)
        )
    else:
        lines.append("- none")
    lines.extend(["", "drafts_created:"])
    lines.extend(f"- {name}" for name in drafted) if drafted else lines.append("- none")
    status_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative Mac Mini-native lead research worker for JVT.")
    parser.add_argument("--root", type=Path, default=Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"))
    parser.add_argument("--queries-per-run", type=int, default=4)
    parser.add_argument("--results-per-query", type=int, default=8)
    parser.add_argument("--max-new-leads", type=int, default=10)
    parser.add_argument("--draft-limit", type=int, default=5)
    parser.add_argument(
        "--model-screen",
        choices=["off", "optional"],
        default=os.environ.get("JVT_RESEARCH_MODEL_SCREEN", "optional"),
    )
    parser.add_argument(
        "--model-screen-profiles",
        default=os.environ.get("JVT_RESEARCH_MODEL_SCREEN_PROFILES", DEFAULT_MODEL_SCREEN_PROFILES),
    )
    parser.add_argument(
        "--model-screen-timeout",
        type=int,
        default=int(os.environ.get("JVT_RESEARCH_MODEL_SCREEN_TIMEOUT", "900")),
    )
    parser.add_argument(
        "--lanes",
        default="",
        help="Optional comma-separated source lanes to run, for example: dental_voice,it_ballot,local_receptionist",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    db_path = root / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
    data_dir = root / "lead-pipeline" / "data"
    state_path = root / "lead-pipeline" / "state" / "auto-research-state.json"
    status_path = root / "lead-pipeline" / "state" / "auto-research-status.md"

    existing_names, existing_hosts = load_existing(db_path)
    state = load_state(state_path)
    seen_domains = set(state.get("seen_domains", []))
    lanes = [lane.strip() for lane in args.lanes.split(",") if lane.strip()]
    unknown_lanes = [lane for lane in lanes if lane not in LANE_QUERIES]
    if unknown_lanes:
        raise SystemExit(f"Unknown lane(s): {', '.join(unknown_lanes)}")
    queries = pick_queries(state, args.queries_per_run, lanes or None)

    candidates: list[dict[str, str]] = []
    for picked_query in queries:
        lane = picked_query["lane"]
        query = picked_query["query"]
        for result in search(query, args.results_per_query):
            homepage = normalize_homepage(result["url"])
            if not homepage:
                continue
            host = domain(homepage)
            if host in existing_hosts or host in seen_domains:
                continue
            homepage_html = fetch_html(homepage)
            if not homepage_html:
                seen_domains.add(host)
                continue
            homepage_title = extract_title(homepage_html)
            homepage_meta_names = extract_meta_site_names(homepage_html)
            homepage_jsonld_names = extract_jsonld_names(homepage_html)
            contact_page = extract_contact_link(homepage, homepage_html)
            contact_html = fetch_html(contact_page) if contact_page and contact_page != homepage else homepage_html
            contact_title = extract_title(contact_html) if contact_html else ""
            contact_meta_names = extract_meta_site_names(contact_html) if contact_html else []
            contact_jsonld_names = extract_jsonld_names(contact_html) if contact_html else []
            company_name = choose_company_name(
                *homepage_meta_names,
                *homepage_jsonld_names,
                *contact_meta_names,
                *contact_jsonld_names,
                homepage_title,
                contact_title,
                host=host,
            )
            if not company_name:
                seen_domains.add(host)
                continue
            company_key = company_name.strip().lower()
            if company_key in existing_names:
                seen_domains.add(host)
                continue
            combined = "\n".join([result["title"], result["snippet"], homepage_html[:120000], contact_html[:120000]])
            practice_areas = detect_practice_areas(combined)
            industry = infer_industry(combined, practice_areas)
            expected_industries = LANE_EXPECTED_INDUSTRIES.get(lane)
            if expected_industries and industry not in expected_industries:
                seen_domains.add(host)
                continue
            public_email = pick_public_email(extract_emails(combined))
            if not public_email:
                seen_domains.add(host)
                continue
            if not email_matches_host(public_email, host):
                seen_domains.add(host)
                continue
            if not has_name_domain_overlap(company_name, host, public_email):
                seen_domains.add(host)
                continue
            fit_score = score_fit(combined, contact_page, public_email, practice_areas, industry)
            if fit_score < 80 or not practice_areas:
                seen_domains.add(host)
                continue
            city_state = find_city_state(result["snippet"], contact_html, homepage_html)
            row = {
                "company_name": company_name,
                "website": homepage,
                "city_state": city_state,
                "industry": industry,
                "practice_area": ", ".join(practice_areas),
                "contact_page": contact_page,
                "public_email": public_email,
                "notes": build_note(industry, practice_areas, public_email, contact_page, homepage),
                "fit_score": str(fit_score),
                "outreach_status": "new",
                "follow_up_status": "none",
                "last_touched_date": "",
            }
            candidates.append(row)
            existing_hosts.add(host)
            existing_names.add(company_key)
            seen_domains.add(host)
            if len(candidates) >= args.max_new_leads:
                break
        if len(candidates) >= args.max_new_leads:
            break

    model_screen_runs: list[dict] = []
    added = candidates
    if args.model_screen != "off" and candidates:
        profiles = parse_profiles(args.model_screen_profiles)
        added, model_screen_runs = run_model_screen(
            root,
            root / "lead-pipeline" / "state",
            candidates,
            profiles,
            args.model_screen_timeout,
        )

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    csv_path = None
    drafted: list[str] = []
    if added:
        csv_path = data_dir / f"{timestamp}-auto-research-targets.csv"
        latest_path = data_dir / "latest-auto-research-targets.csv"
        write_csv(csv_path, added)
        write_csv(latest_path, added)
        import_csv(db_path, csv_path, root)
        drafted = generate_drafts(root, db_path, added, args.draft_limit)

    state["seen_domains"] = sorted(seen_domains)
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    save_state(state_path, state)
    total_leads = fetch_total_leads(db_path)
    write_status(status_path, queries=queries, csv_path=csv_path, added=added, total_leads=total_leads, drafted=drafted, model_screen_runs=model_screen_runs)
    print(f"queries={len(queries)} candidates={len(candidates)} added={len(added)} total_leads={total_leads}")
    if csv_path:
        print(csv_path)


if __name__ == "__main__":
    main()
