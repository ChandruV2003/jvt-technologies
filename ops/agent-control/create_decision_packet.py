#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control")
PENDING_DIR = ROOT / "pending"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "decision"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a human decision packet for JVT agent control")
    parser.add_argument("category", help="Short category such as outreach, finance, pricing, infra")
    parser.add_argument("title", help="Human-readable decision title")
    parser.add_argument("recommended_action", help="Recommended action in one sentence")
    parser.add_argument("--context", default="", help="Optional context summary")
    parser.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--options", action="append", default=[], help="One option per flag; may be repeated")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d")
    stem = f"{stamp}-{slugify(args.title)}"
    json_path = PENDING_DIR / f"{stem}.json"
    md_path = PENDING_DIR / f"{stem}.md"
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": "pending",
        "category": args.category,
        "title": args.title,
        "recommended_action": args.recommended_action,
        "context": args.context,
        "risk": args.risk,
        "options": args.options,
        "created_at": now.isoformat(),
        "stem": stem,
        "paths": {
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }

    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    option_lines = "\n".join(f"- {option}" for option in args.options) if args.options else "- Accept the recommended action\n- Reject and revise scope\n- Defer pending more context"
    markdown = f"""# {args.title}

- Category: `{args.category}`
- Status: `pending`
- Risk: `{args.risk}`
- Created: `{now.isoformat()}`

## Recommended Action

{args.recommended_action}

## Context

{args.context or "No extra context provided."}

## Options

{option_lines}
"""
    md_path.write_text(markdown, encoding="utf-8")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
