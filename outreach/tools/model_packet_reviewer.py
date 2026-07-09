#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


NON_OVERRIDABLE_MARKERS = (
    "invalid recipient email",
    "missing company name",
    "internal/test company",
    "internal recipient",
    "blocked recipient local part",
    "email domain does not match contact page domain",
    "careers/recruiting contact page",
    "not an initial packet",
    "not a follow-up packet",
    "missing subject",
    "missing rendered message artifact",
)


def has_non_overridable_reasons(reasons: list[str]) -> bool:
    lowered = " | ".join(reason.lower() for reason in reasons)
    return any(marker in lowered for marker in NON_OVERRIDABLE_MARKERS)


def model_configured() -> bool:
    return os.environ.get("JVT_PACKET_REVIEW_MODEL_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


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


def packet_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_name": payload.get("company_name"),
        "recipient_email": payload.get("recipient_email") or payload.get("public_email"),
        "industry": payload.get("industry"),
        "practice_area": payload.get("practice_area"),
        "contact_page": payload.get("contact_page") or payload.get("website"),
        "subject": payload.get("subject"),
        "follow_up_stage": payload.get("follow_up_stage"),
        "follow_up_parent_stem": payload.get("follow_up_parent_stem"),
        "quality_hold_reason": payload.get("quality_hold_reason"),
    }


def load_message_preview(payload: dict[str, Any], max_chars: int = 600) -> str:
    for key in ("review_path", "text_path"):
        raw = payload.get(key)
        if not raw:
            continue
        path = Path(str(raw))
        try:
            if path.exists():
                return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except OSError:
            continue
    return ""


def mlx_generate(prompt: str) -> dict[str, Any]:
    if not model_configured():
        return {"available": False, "reason": "JVT_PACKET_REVIEW_MODEL_ENABLED disabled"}
    host = (
        os.environ.get("JVT_PACKET_REVIEW_MLX_HOST")
        or os.environ.get("JVT_MLX_HOST")
        or "http://127.0.0.1:11435"
    ).rstrip("/")
    model = (
        os.environ.get("JVT_PACKET_REVIEW_MLX_MODEL")
        or os.environ.get("JVT_MLX_MODEL")
        or "mlx-community/Qwen3-8B-4bit"
    )
    timeout_seconds = float(os.environ.get("JVT_PACKET_REVIEW_TIMEOUT_SECONDS") or "90")
    num_predict = int(os.environ.get("JVT_PACKET_REVIEW_NUM_PREDICT") or "90")
    request = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.0,
                "max_tokens": num_predict,
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
        "response": str(message.get("content") or "").strip(),
    }


def ollama_generate(prompt: str) -> dict[str, Any]:
    if not model_configured():
        return {"available": False, "reason": "JVT_PACKET_REVIEW_MODEL_ENABLED disabled"}
    host = (
        os.environ.get("JVT_PACKET_REVIEW_OLLAMA_HOST")
        or os.environ.get("JVT_OLLAMA_HOST")
        or os.environ.get("OLLAMA_HOST")
        or "http://100.94.111.27:11434"
    ).rstrip("/")
    model = (
        os.environ.get("JVT_PACKET_REVIEW_MODEL")
        or os.environ.get("JVT_AI_DIRECTOR_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or "qwen2.5:1.5b"
    )
    timeout_seconds = float(os.environ.get("JVT_PACKET_REVIEW_TIMEOUT_SECONDS") or "45")
    num_predict = int(os.environ.get("JVT_PACKET_REVIEW_NUM_PREDICT") or "90")
    request = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": num_predict},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": str(exc)}
    return {"available": True, "model": model, "response": str(data.get("response") or "").strip()}


def model_generate(prompt: str) -> dict[str, Any]:
    if os.environ.get("JVT_PACKET_REVIEW_BACKEND", "mlx").strip().lower() == "ollama":
        return ollama_generate(prompt)
    result = mlx_generate(prompt)
    if result.get("available"):
        return result
    fallback = ollama_generate(prompt)
    if fallback.get("available"):
        fallback["fallback_from"] = result
        return fallback
    return result


def review_packet(payload: dict[str, Any], reasons: list[str], packet_type: str) -> dict[str, Any]:
    if not reasons:
        return {
            "available": False,
            "approved": False,
            "confidence": 0,
            "reason": "deterministic rules already passed; model not needed",
        }
    if has_non_overridable_reasons(reasons):
        return {
            "available": False,
            "approved": False,
            "confidence": 0,
            "reason": "non-overridable deterministic veto present",
        }

    prompt = "\n".join(
        [
            "You are the local JVT Technologies outreach approval reviewer.",
            "The deterministic hard safety gates already passed before this prompt. You are reviewing only soft hold reasons.",
            "Approve borderline outreach packets when the structured fields show a real target customer and the hold reason is only a soft naming/formatting concern.",
            "Hold if the business still does not look like a real target customer, the recipient looks unrelated, the copy is spammy, or facts are uncertain.",
            "Target customers: law firms, accounting/tax firms, title/mortgage services, property management, construction/contracting, and adjacent document-heavy service businesses.",
            "Treat the industry field as useful evidence, not as a guarantee. A company name containing Law, Legal, CPA, Tax, Accounting, Title, Mortgage, Property, Construction, or Contracting is useful supporting evidence.",
            "Soft reasons you should normally approve: awkward but plausible company name, trailing punctuation, overly cautious generic-name pattern, likely unnormalized CPA capitalization, or long but real company name.",
            "If the only concerns are soft naming reasons and the company_name or industry clearly indicates a target customer, return approve=true with confidence 80-90.",
            "Return only JSON with keys: approve boolean, confidence integer 0-100, reason short string.",
            "Approve when confidence is 80 or higher.",
            "",
            f"Packet type: {packet_type}",
            f"Deterministic hold reasons: {json.dumps(reasons)}",
            f"Packet summary: {json.dumps(packet_summary(payload), ensure_ascii=False)}",
            f"Message preview: {load_message_preview(payload)}",
        ]
    )
    result = model_generate(prompt)
    if not result.get("available"):
        return {**result, "approved": False, "confidence": 0}
    try:
        parsed = extract_json_object(str(result.get("response") or ""))
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            **result,
            "approved": False,
            "confidence": 0,
            "reason": f"model JSON parse failed: {exc}",
        }
    confidence = int(parsed.get("confidence") or 0)
    approved = bool(parsed.get("approve")) and confidence >= int(os.environ.get("JVT_PACKET_REVIEW_MIN_CONFIDENCE") or "80")
    return {
        "available": True,
        "backend": result.get("backend") or "ollama",
        "model": result.get("model"),
        "approved": approved,
        "confidence": confidence,
        "reason": str(parsed.get("reason") or "").strip()[:300],
        "raw_decision": parsed,
    }
