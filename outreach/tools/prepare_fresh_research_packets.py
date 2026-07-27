#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
TOOLS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_ROOT))

from generate_daily_wave import (  # noqa: E402
    lead_rejection_reasons,
    packet_stem,
    queued_lead_ids,
    run_generate_draft,
)
from packet_quality import classify_packet, stamp_packet_quality  # noqa: E402


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def find_lead(conn: sqlite3.Connection, item: dict[str, Any]) -> sqlite3.Row | None:
    company = str(item.get("company_name") or "").strip()
    website = str(item.get("website") or "").strip()
    if not company:
        return None
    if website:
        row = conn.execute(
            """
            SELECT *
            FROM leads
            WHERE lower(company_name) = lower(?) AND website = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (company, website),
        ).fetchone()
        if row:
            return row
    return conn.execute(
        """
        SELECT *
        FROM leads
        WHERE lower(company_name) = lower(?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (company,),
    ).fetchone()


def write_report(state_root: Path, report: dict[str, Any]) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    json_path = state_root / "latest-fresh-lead-packet-prep.json"
    md_path = state_root / "latest-fresh-lead-packet-prep.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Fresh Lead Packet Prep",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Research generation: `{report.get('source_research_generated_at')}`",
        f"- Latest researched leads: `{report.get('source_lead_count')}`",
        f"- Staged in review: `{report.get('staged_count')}`",
        f"- Approval candidates: `{report.get('approval_candidate_count')}`",
        f"- Skipped: `{report.get('skipped_count')}`",
        "",
        "## Staged",
        "",
    ]
    for item in report.get("staged", []):
        lines.append(
            f"- `{item['stem']}` - {item['company_name']} - `{item['decision']}` - score `{item['score']}`"
        )
    if not report.get("staged"):
        lines.append("- None.")
    lines.extend(["", "## Skipped", ""])
    for item in report.get("skipped", []):
        lines.append(f"- {item.get('company_name') or 'Unknown'} - {', '.join(item.get('reasons') or [])}")
    if not report.get("skipped"):
        lines.append("- None.")
    lines.extend([
        "",
        "## Guardrail",
        "",
        "Packets are staged in review only. This workflow does not approve or deliver email.",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")


def prepare_packets(
    *,
    root: Path,
    status_path: Path,
    db_path: Path,
    max_packets: int,
    min_fit_score: int,
    dry_run: bool,
) -> dict[str, Any]:
    source = load_json(status_path, {})
    latest = source.get("new_leads") if isinstance(source.get("new_leads"), list) else []
    queue_root = root / "outreach" / "queue"
    output_dir = queue_root / "review"
    state_root = root / "ops" / "agent-control" / "state"
    packet_date = date.today().isoformat()
    skip_ids = queued_lead_ids(queue_root)
    staged: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for item in latest:
            if len(staged) >= max_packets:
                break
            row = find_lead(conn, item if isinstance(item, dict) else {})
            if row is None:
                skipped.append({
                    "company_name": str((item or {}).get("company_name") or "") if isinstance(item, dict) else "",
                    "reasons": ["lead not found in database"],
                })
                continue
            reasons = lead_rejection_reasons(row, skip_ids, min_fit_score, False)
            if reasons:
                skipped.append({
                    "lead_id": row["id"],
                    "company_name": row["company_name"],
                    "reasons": reasons,
                })
                continue
            stem = packet_stem(packet_date, row["company_name"], root / "outreach" / "templates" / "initial-introduction.md")
            if dry_run:
                staged.append({
                    "lead_id": row["id"],
                    "company_name": row["company_name"],
                    "stem": stem,
                    "decision": "would_stage",
                    "score": None,
                })
                continue
            run_generate_draft(
                root,
                db_path,
                root / "outreach" / "templates" / "initial-introduction.md",
                output_dir,
                int(row["id"]),
                packet_date,
                "team",
                "hello@jvt-technologies.com",
                "https://jvt-technologies.com",
                "Chandru Vasudevan",
                "Founder",
                "JVT Technologies LLC",
            )
            metadata_path = output_dir / f"{stem}.json"
            payload = load_json(metadata_path, {})
            quality = classify_packet(payload, source_queue="review")
            stamp_packet_quality(payload, quality)
            payload["fresh_research_source_generated_at"] = source.get("generated_at")
            payload["fresh_research_packetized_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            staged.append({
                "lead_id": row["id"],
                "company_name": row["company_name"],
                "stem": stem,
                "decision": quality["decision"],
                "score": quality["score"],
            })
            skip_ids.add(int(row["id"]))
    finally:
        conn.close()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ok": True,
        "dry_run": dry_run,
        "source_research_generated_at": source.get("generated_at"),
        "source_lead_count": len(latest),
        "staged_count": len(staged),
        "approval_candidate_count": sum(1 for item in staged if item.get("decision") == "approval_candidate"),
        "skipped_count": len(skipped),
        "staged": staged,
        "skipped": skipped,
        "guardrail": "Review-only packet staging. No approval or delivery.",
    }
    write_report(state_root, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage the latest qualified research leads as review-only packets.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--status", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--max-packets", type=int, default=5)
    parser.add_argument("--min-fit-score", type=int, default=85)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    status_path = args.status or args.root / "lead-pipeline" / "state" / "auto-research-status.json"
    db_path = args.db or args.root / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
    report = prepare_packets(
        root=args.root,
        status_path=status_path,
        db_path=db_path,
        max_packets=max(1, min(10, args.max_packets)),
        min_fit_score=max(0, args.min_fit_score),
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
