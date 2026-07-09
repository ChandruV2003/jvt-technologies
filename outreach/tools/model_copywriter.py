#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_SITE_URL = "https://jvt-technologies.com"
DEFAULT_MODEL = "mlx-community/Qwen3-8B-4bit"


def copywriter_enabled() -> bool:
    return os.environ.get("JVT_COPYWRITER_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise
        payload = json.loads(match.group(0))
    return payload if isinstance(payload, dict) else {}


def call_mlx(prompt: str) -> dict[str, Any]:
    if not copywriter_enabled():
        return {"available": False, "reason": "JVT_COPYWRITER_ENABLED disabled"}
    host = (
        os.environ.get("JVT_COPYWRITER_MLX_HOST")
        or os.environ.get("JVT_MLX_HOST")
        or "http://127.0.0.1:11435"
    ).rstrip("/")
    model = os.environ.get("JVT_COPYWRITER_MLX_MODEL") or os.environ.get("JVT_MLX_MODEL") or DEFAULT_MODEL
    timeout_seconds = float(os.environ.get("JVT_COPYWRITER_TIMEOUT_SECONDS") or "180")
    max_tokens = int(os.environ.get("JVT_COPYWRITER_MAX_TOKENS") or "900")
    temperature = float(os.environ.get("JVT_COPYWRITER_TEMPERATURE") or "0.55")
    request = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"available": False, "backend": "m4-mlx", "reason": str(exc)}
    choices = data.get("choices") or []
    message = ((choices[0] or {}).get("message") or {}) if choices else {}
    return {
        "available": True,
        "backend": "m4-mlx",
        "model": model,
        "host": host,
        "response": str(message.get("content") or "").strip(),
    }


def fallback_subject(packet: dict[str, Any], packet_type: str) -> str:
    company = str(packet.get("company_name") or "your team").strip()
    if packet_type == "initial":
        return f"A workflow cleanup idea for {company}"
    return f"Re: Workflow cleanup for {company}"


def build_prompt(
    packet: dict[str, Any],
    *,
    packet_type: str,
    subject: str,
    body: str,
    site_url: str,
) -> str:
    company = str(packet.get("company_name") or "your team").strip()
    industry = str(packet.get("industry") or "").strip()
    practice_area = str(packet.get("practice_area") or "").strip()
    likely_pain = str(packet.get("likely_pain") or "").strip()
    personalized_offer = str(packet.get("personalized_offer") or "").strip()
    public_context = str(packet.get("public_context") or "").strip()
    fit_reason = str(packet.get("fit_reason") or "").strip()
    recipient = str(packet.get("recipient_email") or packet.get("public_email") or "").strip()
    return "\n".join(
        [
            "You are JVT Technologies' local outreach copywriter.",
            "Rewrite the email so it sounds modern, direct, and human, with slight Gen-Z/plainspoken energy, but still credible for law, accounting, title, property, and other professional-service teams.",
            "Do not sound like a fake AI startup, do not overhype, and do not use slang like bruh, fire, lol, gamechanger, or revolutionary.",
            "Do not invent facts about the company. Use only the supplied structured facts.",
            "Keep it short: 110-180 words for initial emails, 80-140 words for follow-ups.",
            "Include a clear concrete workflow angle. Prefer phrases like messy inboxes, intake details, meeting notes, document questions, reviewed packet, and demo lab.",
            "Do not promise integrations, ROI, legal/tax/financial advice, autonomous client communication, or live phone setup.",
            "Every client-facing action must stay human-reviewed.",
            "Keep a soft ask: offer to send one concrete example or let them skim the demo lab. Do not pressure for a meeting first.",
            "Return only JSON with keys: subject, body, score, reason.",
            "Score must be an integer from 0 to 100, not a 0-10 rating.",
            "The body must be plain text, include greeting and signature, and use real newlines. Signature must be Chandru Vasudevan / Founder, JVT Technologies LLC.",
            "",
            f"Packet type: {packet_type}",
            f"Company: {company}",
            f"Recipient: {recipient}",
            f"Industry: {industry}",
            f"Practice area: {practice_area}",
            f"Likely pain: {likely_pain}",
            f"Personalized offer: {personalized_offer}",
            f"Public context: {public_context}",
            f"Fit reason: {fit_reason}",
            f"Demo lab URL: {site_url.rstrip('/')}/#demos",
            "",
            f"Current subject: {subject}",
            "Current body:",
            body[:2500],
        ]
    )


def normalize_body(body: str) -> str:
    cleaned = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned + "\n"


def validate_rewrite(subject: str, body: str) -> list[str]:
    reasons: list[str] = []
    if not subject or len(subject) > 90:
        reasons.append("subject missing or too long")
    if not body or len(body) < 220:
        reasons.append("body too short")
    if len(body) > 1800:
        reasons.append("body too long")
    lowered = body.lower()
    blocked = (
        "guarantee",
        "revolutionary",
        "gamechanger",
        "legal advice",
        "tax advice",
        "financial advice",
        "fully autonomous",
        "no human",
        "bruh",
        "lol",
    )
    found = [term for term in blocked if term in lowered]
    if found:
        reasons.append(f"blocked wording: {', '.join(found)}")
    if "chandru vasudevan" not in lowered or "jvt technologies" not in lowered:
        reasons.append("missing required signature")
    return reasons


def rewrite_email(
    packet: dict[str, Any],
    *,
    packet_type: str,
    subject: str,
    body: str,
    site_url: str = DEFAULT_SITE_URL,
) -> dict[str, Any]:
    prompt = build_prompt(packet, packet_type=packet_type, subject=subject, body=body, site_url=site_url)
    result = call_mlx(prompt)
    if not result.get("available"):
        return {**result, "rewritten": False, "subject": subject, "body": body, "validation_reasons": ["model unavailable"]}
    try:
        parsed = extract_json_object(str(result.get("response") or ""))
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            **result,
            "rewritten": False,
            "subject": subject,
            "body": body,
            "validation_reasons": [f"model JSON parse failed: {exc}"],
        }
    new_subject = str(parsed.get("subject") or fallback_subject(packet, packet_type)).strip()
    new_body = normalize_body(str(parsed.get("body") or body))
    validation_reasons = validate_rewrite(new_subject, new_body)
    score = int(parsed.get("score") or 0)
    if 1 <= score <= 10:
        score *= 10
    if validation_reasons or score < int(os.environ.get("JVT_COPYWRITER_MIN_SCORE") or "70"):
        return {
            **result,
            "rewritten": False,
            "subject": subject,
            "body": body,
            "candidate_subject": new_subject,
            "candidate_body": new_body,
            "score": score,
            "reason": str(parsed.get("reason") or "").strip()[:300],
            "validation_reasons": validation_reasons or [f"score below threshold: {score}"],
        }
    return {
        **result,
        "rewritten": True,
        "subject": new_subject,
        "body": new_body,
        "score": score,
        "reason": str(parsed.get("reason") or "").strip()[:300],
        "validation_reasons": [],
    }


def packet_type_for(payload: dict[str, Any]) -> str:
    return "follow-up" if payload.get("follow_up_stage") or payload.get("follow_up_parent_stem") else "initial"
