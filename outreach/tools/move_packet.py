#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/queue")
VALID_STATUSES = {"draft", "review", "approved", "sent", "replied"}


def packet_paths(queue_dir: Path, stem: str) -> list[Path]:
    return sorted(path for path in queue_dir.glob(f"{stem}.*") if path.is_file())


def update_metadata_paths(data: dict[str, object], target_dir: Path, stem: str) -> dict[str, object]:
    key_to_suffix = {
        "review_path": ".md",
        "text_path": ".txt",
        "html_path": ".html",
    }
    for key, suffix in key_to_suffix.items():
        if key in data:
            data[key] = str(target_dir / f"{stem}{suffix}")
    return data


def update_review_markdown(path: Path, target_status: str) -> None:
    if not path.exists() or path.suffix != ".md":
        return
    content = path.read_text(encoding="utf-8")
    updated = re.sub(r"^status:\s+\w+\s*$", f"status: {target_status}", content, flags=re.MULTILINE)
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Move an outreach packet between queue states")
    parser.add_argument("--stem", required=True, help="Packet basename without extension")
    parser.add_argument("--from", dest="source", required=True, choices=sorted(VALID_STATUSES))
    parser.add_argument("--to", dest="target", required=True, choices=sorted(VALID_STATUSES))
    args = parser.parse_args()

    if args.source == args.target:
        raise SystemExit("Source and target queues must differ")

    source_dir = ROOT / args.source
    target_dir = ROOT / args.target
    target_dir.mkdir(parents=True, exist_ok=True)

    paths = packet_paths(source_dir, args.stem)
    if not paths:
        raise SystemExit(f"No packet files found for {args.stem} in {source_dir}")

    for path in paths:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            data["status"] = args.target
            data = update_metadata_paths(data, target_dir, args.stem)
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        elif path.suffix == ".md":
            update_review_markdown(path, args.target)

    moved: list[Path] = []
    for path in paths:
        destination = target_dir / path.name
        path.rename(destination)
        moved.append(destination)

    for path in moved:
        print(path)


if __name__ == "__main__":
    main()
