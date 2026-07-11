#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipient_quality import evidence_gate, lead_payload


DEFAULT_ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")


def audit_payload(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    reasons, evidence = evidence_gate(lead_payload(payload))
    return {
        "name": name,
        "company_name": payload.get("company_name"),
        "recipient_email": payload.get("recipient_email") or payload.get("public_email"),
        "industry": payload.get("industry"),
        "decision": "hold" if reasons else "pass",
        "reasons": reasons,
        "recipient_kind": evidence.get("recipient_kind"),
        "score": evidence.get("score"),
    }


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = Counter(item["decision"] for item in items)
    reasons = Counter(reason for item in items for reason in item["reasons"])
    return {
        "total": len(items),
        "pass": decisions.get("pass", 0),
        "hold": decisions.get("hold", 0),
        "top_hold_reasons": [{"reason": reason, "count": count} for reason, count in reasons.most_common(20)],
        "pass_samples": [item for item in items if item["decision"] == "pass"][:20],
        "hold_samples": [item for item in items if item["decision"] == "hold"][:20],
    }


def audit_db_leads(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM leads
        WHERE outreach_status = 'new'
        ORDER BY fit_score DESC, id ASC
        """
    ).fetchall()
    conn.close()
    return [audit_payload(f"lead:{row['id']}", {key: row[key] for key in row.keys()}) for row in rows]


def audit_queue(queue_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not queue_dir.exists():
        return items
    for path in sorted(queue_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            items.append(
                {
                    "name": path.name,
                    "company_name": "",
                    "recipient_email": "",
                    "industry": "",
                    "decision": "hold",
                    "reasons": ["invalid queue metadata json"],
                    "recipient_kind": "",
                    "score": 0,
                }
            )
            continue
        items.append(audit_payload(path.name, payload))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only audit for JVT lead and recipient evidence quality.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    output_path = args.json_out or root / "ops/agent-control/state/latest-lead-quality-audit.json"
    sections = {
        "new_leads": audit_db_leads(root / "lead-pipeline/data/jvt_leads.sqlite3"),
        "draft": audit_queue(root / "outreach/queue/draft"),
        "review": audit_queue(root / "outreach/queue/review"),
        "approved": audit_queue(root / "outreach/queue/approved"),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "sections": {name: summarize(items) for name, items in sections.items()},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
