#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from mlx_lm import generate, load


DEFAULT_MODEL_PATH = "/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--Qwen2.5-3B-Instruct-4bit"
DEFAULT_OUTPUT_DIR = "/Users/c.s.d.v.r.s./Developer/Control-Host/Private-AI-Lab/JVT-Technologies/outreach/queue/review"


SYSTEM_PROMPT = """You are a careful assistant for JVT Technologies.
Write a short professional email reply draft.
Rules:
- do not promise features that are not confirmed
- do not make pricing commitments
- do not claim a demo is booked unless the human said so
- keep the tone warm, practical, and consultant-like
- if the inbound message asks for a demo, suggest a short focused demo
- if information is missing, keep the reply conservative
- sign the reply as:
Chandru Vasu
Founder, JVT Technologies
- output only the email body, no subject line, no markdown, no code fences, no placeholders
"""


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def load_message(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_prompt(message: dict[str, str]) -> str:
    return "\n".join(
        [
            SYSTEM_PROMPT,
            "",
            f"From: {message.get('from', '')}",
            f"Subject: {message.get('subject', '')}",
            f"Date: {message.get('date', '')}",
            "",
            "Inbound snippet:",
            message.get("snippet", ""),
            "",
            "Write the reply body now.",
        ]
    )


def clean_reply(body: str) -> str:
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
    cleaned = re.sub(r"\n(Best regards,?|Best,?)\n.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = cleaned.rstrip() + "\n\nBest,\nChandru Vasu\nFounder, JVT Technologies"
    return cleaned.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a reviewed reply from an imported inbound email")
    parser.add_argument("--message-json", required=True, type=Path)
    parser.add_argument("--model-path", default=env("LOCAL_DRAFT_MODEL_PATH", DEFAULT_MODEL_PATH))
    parser.add_argument("--output-dir", type=Path, default=Path(env("REPLY_DRAFT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)))
    args = parser.parse_args()

    message = load_message(args.message_json)
    model, tokenizer = load(args.model_path)
    prompt = build_prompt(message)
    body = generate(model, tokenizer, prompt=prompt, max_tokens=220, verbose=False).strip()
    body = clean_reply(body)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.message_json.stem
    output_path = args.output_dir / f"{stem}-reply-draft.md"
    output_path.write_text(
        "\n".join(
            [
                f"source_message: {args.message_json}",
                f"generated_at: {datetime.now().isoformat(timespec='seconds')}",
                "status: review",
                "mode: local-draft",
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
