#!/usr/bin/env python3

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
OUTREACH_ROOT = ROOT / "outreach"
QUEUE_ROOT = OUTREACH_ROOT / "queue"
INBOX_ROOT = OUTREACH_ROOT / "inbox" / "new"
CONTROL_ROOT = ROOT / "ops" / "agent-control"
DB_PATH = ROOT / "lead-pipeline" / "data" / "jvt_leads.sqlite3"


def count_json_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len([path for path in directory.glob("*.json") if path.is_file()])


def json_stems(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.json") if path.is_file())


def lead_counts() -> dict[str, int]:
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT outreach_status, COUNT(*) FROM leads GROUP BY outreach_status").fetchall()
    conn.close()
    return {status or "unknown": count for status, count in rows}


def main() -> None:
    payload = {
        "lead_counts": lead_counts(),
        "queue_counts": {
            "draft": count_json_files(QUEUE_ROOT / "draft"),
            "review": count_json_files(QUEUE_ROOT / "review"),
            "approved": count_json_files(QUEUE_ROOT / "approved"),
            "sent": count_json_files(QUEUE_ROOT / "sent"),
            "replied": count_json_files(QUEUE_ROOT / "replied"),
        },
        "inbox_new_count": count_json_files(INBOX_ROOT),
        "decision_counts": {
            "pending": count_json_files(CONTROL_ROOT / "pending"),
            "approved": count_json_files(CONTROL_ROOT / "approved"),
            "rejected": count_json_files(CONTROL_ROOT / "rejected"),
            "executed": count_json_files(CONTROL_ROOT / "executed"),
        },
        "pending_decisions": json_stems(CONTROL_ROOT / "pending"),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
