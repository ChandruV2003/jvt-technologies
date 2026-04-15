#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control")
DIRS = {
    "pending": ROOT / "pending",
    "approved": ROOT / "approved",
    "rejected": ROOT / "rejected",
    "executed": ROOT / "executed",
}
LOG_PATH = ROOT / "decision-log.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Move a decision packet through the agent-control state machine")
    parser.add_argument("stem", help="Packet stem without extension")
    parser.add_argument("state", choices=["approved", "rejected", "executed"])
    parser.add_argument("note", nargs="?", default="", help="Optional operator note")
    args = parser.parse_args()

    source_json = None
    source_md = None
    source_dir_name = None
    for dir_name, directory in DIRS.items():
        candidate_json = directory / f"{args.stem}.json"
        candidate_md = directory / f"{args.stem}.md"
        if candidate_json.exists():
            source_json = candidate_json
            source_md = candidate_md
            source_dir_name = dir_name
            break

    if source_json is None or source_md is None:
        raise SystemExit(f"Could not find decision packet for stem: {args.stem}")

    payload = json.loads(source_json.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).isoformat()
    payload["status"] = args.state
    payload["operator_note"] = args.note
    payload["updated_at"] = now

    target_dir = DIRS[args.state]
    target_dir.mkdir(parents=True, exist_ok=True)
    target_json = target_dir / source_json.name
    target_md = target_dir / source_md.name

    target_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    source_json.unlink()

    markdown = source_md.read_text(encoding="utf-8").rstrip() + f"\n\n## Decision Update\n\n- New status: `{args.state}`\n- Updated: `{now}`\n- Note: {args.note or 'No note provided.'}\n"
    target_md.write_text(markdown + "\n", encoding="utf-8")
    source_md.unlink()

    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "stem": args.stem,
            "from_state": source_dir_name,
            "to_state": args.state,
            "note": args.note,
            "updated_at": now,
        }) + "\n")

    print(json.dumps({
        "stem": args.stem,
        "from_state": source_dir_name,
        "to_state": args.state,
        "json_path": str(target_json),
        "markdown_path": str(target_md),
    }))


if __name__ == "__main__":
    main()
