#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from email_theme import DEFAULT_REPLY_TO, DEFAULT_SITE_URL, render_text_email_html


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
QUEUE_NAMES = ("draft", "review", "approved")
LEGACY_MARKERS = (
    "background:#f4f0e8",
    "<body>",
    "<!doctype html>",
)


def should_restyle(html_path: Path, force: bool) -> bool:
    if force or not html_path.exists():
        return True
    html_body = html_path.read_text(encoding="utf-8", errors="replace")
    if "jvt-body" in html_body:
        return False
    return any(marker in html_body for marker in LEGACY_MARKERS)


def restyle_packet(metadata_path: Path, force: bool) -> dict[str, object] | None:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "stem": metadata_path.stem,
            "status": "skipped",
            "reason": "metadata_json_parse_error",
        }

    text_path = metadata_path.with_suffix(".txt")
    html_path = metadata_path.with_suffix(".html")
    if not text_path.exists():
        return {
            "stem": metadata_path.stem,
            "status": "skipped",
            "reason": "missing_text_body",
        }
    if not should_restyle(html_path, force):
        return None

    subject = str(metadata.get("subject") or "JVT Technologies")
    company = str(metadata.get("company_name") or "your team").strip() or "your team"
    site_url = str(metadata.get("site_url") or DEFAULT_SITE_URL)
    reply_to_email = str(metadata.get("reply_to_email") or DEFAULT_REPLY_TO)
    text_body = text_path.read_text(encoding="utf-8")
    html_body = render_text_email_html(
        text_body,
        title=subject,
        preheader=f"A short JVT Technologies note for {company}.",
        site_url=site_url,
        reply_to_email=reply_to_email,
    )
    html_path.write_text(html_body + "\n", encoding="utf-8")
    metadata["html_path"] = str(html_path)
    metadata["email_theme"] = "jvt-dark-green-gold-graphite-v2"
    metadata["email_theme_updated_at"] = datetime.now(timezone.utc).isoformat()
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {
        "stem": metadata_path.stem,
        "status": "restyled",
        "queue": metadata_path.parent.name,
        "html_path": str(html_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Restyle unsent JVT outreach HTML packets without touching sent mail.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    queue_root = args.root / "outreach" / "queue"
    results: list[dict[str, object]] = []
    for queue_name in QUEUE_NAMES:
        directory = queue_root / queue_name
        if not directory.exists():
            continue
        for metadata_path in sorted(directory.glob("*.json")):
            result = restyle_packet(metadata_path, args.force)
            if result:
                results.append(result)

    print(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queues": list(QUEUE_NAMES),
        "touched_count": sum(1 for item in results if item.get("status") == "restyled"),
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
