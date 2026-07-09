#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import warnings
from pathlib import Path

# The bundled macOS Python uses LibreSSL. urllib3 emits this warning every time
# MLX imports optional networking helpers, which hides real screening failures.
warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL.*")

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_logits_processors, make_sampler


DEFAULT_STRONG_MODEL_PATH = "/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--Qwen2.5-7B-Instruct-4bit"
DEFAULT_REVIEWER_MODEL_PATH = "/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--gpt-oss-20b-MXFP4-Q4"


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def resolve_model_path(profile: str, explicit_model_path: str) -> tuple[str, str]:
    if explicit_model_path.strip():
        return profile, explicit_model_path.strip()

    normalized = profile.strip().lower() or "strong"
    if normalized == "reviewer":
        return "reviewer", env("LOCAL_DRAFT_REVIEWER_MODEL_PATH", DEFAULT_REVIEWER_MODEL_PATH)
    return "strong", env("LOCAL_DRAFT_STRONG_MODEL_PATH", DEFAULT_STRONG_MODEL_PATH)


def compact_candidate(candidate: dict) -> dict:
    return {
        "index": candidate.get("index"),
        "company_name": candidate.get("company_name", ""),
        "website": candidate.get("website", ""),
        "industry": candidate.get("industry", ""),
        "practice_area": candidate.get("practice_area", ""),
        "city_state": candidate.get("city_state", ""),
        "public_email": candidate.get("public_email", ""),
        "fit_score": candidate.get("fit_score", ""),
        "notes": candidate.get("notes", "")[:700],
    }


def build_user_prompt(candidates: list[dict]) -> str:
    return "\n".join(
        [
            "Screen these potential clients for JVT Technologies LLC.",
            "JVT sells practical AI operations systems for small and mid-size teams: voice intake, inbox/document triage, meeting-to-action packets, workflow cleanup, document generation, private knowledge assistants, and managed AI operations.",
            "",
            "Accepted buyer categories include real operating law firms, accounting/tax/bookkeeping firms, dental or healthcare-admin offices, insurance agencies, property/HOA management teams, IT/AV/ballot-service operators, title/mortgage offices, construction/admin-heavy contractors, and local service teams with missed-call or document-heavy workflows.",
            "Do not reject a dental, insurance, property, IT/ballot, or local-receptionist candidate merely because it is not a law or accounting firm. Judge whether the company looks real, reachable, and plausibly needs one of JVT's current service lines.",
            "",
            "Strong accept signals:",
            "- a real company or practice name, not a page title",
            "- public business inbox on the same domain",
            "- evidence of intake calls, appointments, forms, client documents, board meetings, claims, certificates, packets, scheduling, or other repeated admin work",
            "- small or mid-size team where a narrow paid pilot could be useful",
            "",
            "Reject directories, social pages, generic SEO pages, broad software/SaaS vendors, answering-service competitors unless they are a channel/partner candidate, unclear company names, placeholder emails, recruiting contacts, weak-fit practices, or companies where the row looks machine-extracted rather than real.",
            "",
            "Return only valid JSON. Do not include markdown.",
            "The JSON must be an array with one object per candidate:",
            '{"index": 0, "accept": true, "score": 87, "reason": "short reason", "concerns": ["short concern"]}',
            'Use "score" as your confidence from 0 to 100.',
            "",
            "Candidates:",
            json.dumps([compact_candidate(candidate) for candidate in candidates], indent=2),
        ]
    )


def format_prompt(tokenizer, user_prompt: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are a strict lead-screening assistant. Output only valid JSON. Do not include markdown or commentary.",
        },
        {"role": "user", "content": user_prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            return user_prompt
    return user_prompt


def extract_json_array(text: str) -> list[dict]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    if "<|channel|>final<|message|>" in cleaned:
        cleaned = cleaned.split("<|channel|>final<|message|>")[-1]
        cleaned = cleaned.split("<|end|>", 1)[0].strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, list):
        raise ValueError("Model response was not a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def fallback_rejects(candidates: list[dict], reason: str) -> list[dict]:
    results: list[dict] = []
    for candidate in candidates:
        try:
            index = int(candidate["index"])
        except (KeyError, TypeError, ValueError):
            continue
        results.append(
            {
                "index": index,
                "accept": False,
                "score": 0,
                "reason": reason,
                "concerns": ["Local model response could not be parsed as valid JSON."],
            }
        )
    return results


def normalize_result(result: dict, valid_indexes: set[int]) -> dict | None:
    try:
        index = int(result.get("index"))
    except (TypeError, ValueError):
        return None
    if index not in valid_indexes:
        return None

    try:
        score = int(result.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(score, 100))
    concerns = result.get("concerns", [])
    if not isinstance(concerns, list):
        concerns = [str(concerns)]

    return {
        "index": index,
        "accept": bool(result.get("accept")),
        "score": score,
        "reason": str(result.get("reason", "")).strip()[:320],
        "concerns": [str(item).strip()[:180] for item in concerns if str(item).strip()][:4],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Screen JVT lead candidates with a local MLX model.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", choices=["strong", "reviewer"], default="strong")
    parser.add_argument("--model-path", default="")
    parser.add_argument("--max-tokens", type=int, default=900)
    args = parser.parse_args()

    candidates = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        raise SystemExit("Input must be a JSON list of candidates")
    if not candidates:
        args.output.write_text("[]\n", encoding="utf-8")
        return

    profile, model_path = resolve_model_path(args.profile, args.model_path)
    model, tokenizer = load(model_path)
    prompt = format_prompt(tokenizer, build_user_prompt(candidates))
    response = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=args.max_tokens,
        verbose=False,
        sampler=make_sampler(temp=0.0),
        logits_processors=make_logits_processors(repetition_penalty=1.12, repetition_context_size=80),
    )
    valid_indexes = {int(candidate["index"]) for candidate in candidates}
    parse_error = ""
    try:
        parsed = extract_json_array(response)
    except (json.JSONDecodeError, ValueError) as exc:
        parse_error = f"{exc.__class__.__name__}: {str(exc)[:180]}"
        parsed = fallback_rejects(candidates, "model_response_parse_failed")
    normalized = [item for item in (normalize_result(result, valid_indexes) for result in parsed) if item]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile,
        "model_path": model_path,
        "results": normalized,
    }
    if parse_error:
        payload["parse_error"] = parse_error
        payload["raw_response_preview"] = response[:1200]
    args.output.write_text(
        json.dumps(payload, indent=2)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
