#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def remove_existing_packets(output_dir: Path, lead_ids: set[int], template_name: str) -> None:
    for metadata_path in output_dir.glob("*.json"):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("lead_id") not in lead_ids:
            continue
        if payload.get("template") != template_name:
            continue
        stem = metadata_path.stem
        for sibling in output_dir.glob(f"{stem}.*"):
            if sibling.is_file():
                sibling.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh outreach drafts for selected leads")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--lead-id", required=True, type=int, action="append")
    parser.add_argument("--contact-name", default="team")
    parser.add_argument("--sender-name", default="Chandru Vasudevan")
    parser.add_argument("--sender-title", default="Founder, JVT Technologies")
    parser.add_argument("--sender-company", default="JVT Technologies")
    parser.add_argument("--reply-to-email", default="hello@jvt-technologies.com")
    parser.add_argument("--site-url", default="https://jvt-technologies.com")
    parser.add_argument("--demo-video-url", default="")
    args = parser.parse_args()

    script_path = Path(__file__).resolve().parent / "generate_draft.py"
    lead_ids = list(dict.fromkeys(args.lead_id))
    remove_existing_packets(args.output_dir, set(lead_ids), args.template.name)

    for lead_id in lead_ids:
        command = [
            "python3",
            str(script_path),
            "--db",
            str(args.db),
            "--lead-id",
            str(lead_id),
            "--template",
            str(args.template),
            "--output-dir",
            str(args.output_dir),
            "--contact-name",
            args.contact_name,
            "--reply-to-email",
            args.reply_to_email,
            "--site-url",
            args.site_url,
            "--demo-video-url",
            args.demo_video_url,
            "--sender-name",
            args.sender_name,
            "--sender-title",
            args.sender_title,
            "--sender-company",
            args.sender_company,
        ]
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
