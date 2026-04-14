#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path

from mlx_lm import generate, load


DEFAULT_FAST_MODEL_PATH = "/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--Qwen2.5-3B-Instruct-4bit"
DEFAULT_STRONG_MODEL_PATH = "/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--Qwen2.5-7B-Instruct-4bit"
DEFAULT_OUTPUT_DIR = "/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/queue/review"


SYSTEM_PROMPT = """You are a careful assistant for JVT Technologies.
Write a short professional email reply draft.
Rules:
- do not promise features that are not confirmed
- do not make pricing commitments
- do not claim a demo is booked unless the human said so
- keep the tone warm, practical, and consultant-like
- only use a named greeting if the sender display name is clearly a real person name
- if the sender name is unclear, system-like, or promotional, use "Hello,"
- if the inbound message asks for a demo, suggest a short focused demo
- if information is missing, keep the reply conservative
- sign the reply as:
Chandru Vasu
Founder, JVT Technologies
- output only the email body, no subject line, no markdown, no code fences, no placeholders
"""


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def resolve_model_path(profile: str, explicit_model_path: str) -> tuple[str, str]:
    if explicit_model_path.strip():
        return profile, explicit_model_path.strip()

    normalized = profile.strip().lower() or "fast"
    if normalized == "strong":
        return "strong", env("LOCAL_DRAFT_STRONG_MODEL_PATH", DEFAULT_STRONG_MODEL_PATH)
    return "fast", env("LOCAL_DRAFT_FAST_MODEL_PATH", DEFAULT_FAST_MODEL_PATH)


def load_message(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_prompt(message: dict[str, str]) -> str:
    sender_name = parseaddr(message.get("from", ""))[0].strip()
    return "\n".join(
        [
            SYSTEM_PROMPT,
            "",
            f"From: {message.get('from', '')}",
            f"Sender display name: {sender_name or '(none)'}",
            f"Subject: {message.get('subject', '')}",
            f"Date: {message.get('date', '')}",
            "",
            "Inbound snippet:",
            message.get("snippet", ""),
            "",
            "Write the reply body now.",
        ]
    )


def clean_reply(body: str, sender_name: str) -> str:
    lines = body.splitlines()
    greeting_indexes = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^\s*(hi|hello|dear)\b", line, flags=re.IGNORECASE)
    ]
    if greeting_indexes:
        start = greeting_indexes[0]
        end = greeting_indexes[1] if len(greeting_indexes) > 1 else len(lines)
        lines = lines[start:end]

    cleaned_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if stripped.lower().startswith("subject:"):
            continue
        if "[your name]" in stripped.lower() or "[your position]" in stripped.lower():
            continue
        cleaned_lines.append(line.rstrip())

    cleaned = "\n".join(cleaned_lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"(?im)^dear\s+\[[^\]]+\],\s*$", "Hello,", cleaned)
    cleaned = re.sub(r"(?im)^hi\s+\[[^\]]+\],\s*$", "Hello,", cleaned)
    cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
    cleaned = normalize_greeting(cleaned, sender_name)
    cleaned = re.sub(r"\n(Best regards,?|Best,?)\n.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = cleaned.rstrip() + "\n\nBest,\nChandru Vasu\nFounder, JVT Technologies"
    return cleaned.strip()


def normalize_greeting(body: str, sender_name: str) -> str:
    if not body.strip():
        return body

    lines = body.splitlines()
    if not lines:
        return body

    first_line = lines[0].strip()
    if not re.match(r"^(hi|hello|dear)\b", first_line, flags=re.IGNORECASE):
        return body

    greeting_norm = re.sub(r"[^a-z]+", " ", first_line.lower()).strip()
    sender_tokens = [
        token
        for token in re.sub(r"[^a-z]+", " ", sender_name.lower()).split()
        if len(token) > 1
    ]
    generic_markers = {"team", "support", "listener", "test", "demo", "inquiry", "request"}

    should_genericize = False
    if sender_tokens:
        if not any(token in greeting_norm for token in sender_tokens):
            should_genericize = True
    elif any(marker in greeting_norm for marker in generic_markers):
        should_genericize = True

    if should_genericize:
        lines[0] = "Hello,"
        return "\n".join(lines)
    return body


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a reviewed reply from an imported inbound email")
    parser.add_argument("--message-json", required=True, type=Path)
    parser.add_argument("--model-profile", choices=["fast", "strong"], default=env("LOCAL_DRAFT_MODEL_PROFILE", "fast"))
    parser.add_argument("--model-path", default=env("LOCAL_DRAFT_MODEL_PATH", ""))
    parser.add_argument("--output-dir", type=Path, default=Path(env("REPLY_DRAFT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)))
    args = parser.parse_args()

    message = load_message(args.message_json)
    model_profile, model_path = resolve_model_path(args.model_profile, args.model_path)
    model, tokenizer = load(model_path)
    prompt = build_prompt(message)
    body = generate(model, tokenizer, prompt=prompt, max_tokens=220, verbose=False).strip()
    sender_name = parseaddr(message.get("from", ""))[0].strip()
    body = clean_reply(body, sender_name)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.message_json.stem
    output_path = args.output_dir / f"{stem}-reply-draft-{model_profile}.md"
    output_path.write_text(
        "\n".join(
            [
                f"source_message: {args.message_json}",
                f"generated_at: {datetime.now().isoformat(timespec='seconds')}",
                "status: review",
                "mode: local-draft",
                f"model_profile: {model_profile}",
                f"model_path: {model_path}",
                "",
                body,
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(output_path)


if __name__ == "__main__":
    main()
