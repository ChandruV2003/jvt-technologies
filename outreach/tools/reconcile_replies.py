#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
QUEUE_ROOT = REPO_ROOT / "outreach" / "queue"
INBOX_ROOT = REPO_ROOT / "outreach" / "inbox"
STATE_ROOT = REPO_ROOT / "ops" / "agent-control" / "state"
LEAD_DB = REPO_ROOT / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
REPORT_JSON = STATE_ROOT / "latest-reply-reconciliation.json"
REPORT_MD = STATE_ROOT / "latest-reply-reconciliation.md"
MAILBOX_AGENT_ROOT = REPO_ROOT / "outreach" / "mailbox-agent"
if str(MAILBOX_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MAILBOX_AGENT_ROOT))

from inbox_policy import qualified_external_inbound


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def normalized_subject(value: str) -> str:
    subject = " ".join(value.lower().split())
    while subject.startswith(("re:", "fw:", "fwd:")):
        subject = subject.split(":", 1)[1].strip()
    return subject


def is_qualified_inbound(payload: dict[str, Any]) -> bool:
    return qualified_external_inbound(payload)


def outbound_candidates(sender_email: str, subject: str) -> list[tuple[Path, dict[str, Any]]]:
    wanted_subject = normalized_subject(subject)
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in (QUEUE_ROOT / "sent").glob("*.json"):
        payload = load_json(path, {})
        recipient = str(payload.get("recipient_email") or payload.get("email") or "").lower().strip()
        if recipient != sender_email:
            continue
        outbound_subject = normalized_subject(str(payload.get("subject") or ""))
        if wanted_subject and outbound_subject and wanted_subject != outbound_subject:
            continue
        candidates.append((path, payload))
    return sorted(
        candidates,
        key=lambda item: str(item[1].get("sent_at") or item[1].get("generated_at") or ""),
        reverse=True,
    )


def move_sidecars(stem: str, reply_source: Path, reply: dict[str, Any], *, dry_run: bool) -> list[str]:
    source_dir = QUEUE_ROOT / "sent"
    target_dir = QUEUE_ROOT / "replied"
    paths = sorted(path for path in source_dir.glob(f"{stem}.*") if path.is_file())
    if dry_run:
        return [str(target_dir / path.name) for path in paths]
    target_dir.mkdir(parents=True, exist_ok=True)
    destinations: list[str] = []
    for path in paths:
        destination = target_dir / path.name
        if path.suffix == ".json":
            payload = load_json(path, {})
            payload.update(
                {
                    "status": "replied",
                    "replied_at": reply.get("captured_at") or reply.get("date") or utc_now(),
                    "reply_source_path": str(reply_source),
                    "reply_subject": reply.get("subject") or "",
                    "reply_message_id": str(reply.get("message_id") or "").strip(),
                }
            )
            for key, suffix in (("review_path", ".md"), ("text_path", ".txt"), ("html_path", ".html")):
                if key in payload:
                    payload[key] = str(target_dir / f"{stem}{suffix}")
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        elif path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            lines = ["status: replied" if line.lower().startswith("status:") else line for line in lines]
            path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        path.rename(destination)
        destinations.append(str(destination))
    return destinations


def mark_lead_replied(lead_id: Any, *, dry_run: bool) -> bool:
    if dry_run or not LEAD_DB.exists() or lead_id in (None, ""):
        return False
    conn = sqlite3.connect(LEAD_DB)
    cursor = conn.execute(
        """
        UPDATE leads
        SET outreach_status='replied',
            follow_up_status='responded',
            updated_at=?
        WHERE id=?
        """,
        (utc_now(), int(lead_id)),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def reconcile(*, dry_run: bool = False) -> dict[str, Any]:
    matched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    already_reconciled_sources = {
        str(load_json(path, {}).get("reply_source_path") or "")
        for path in (QUEUE_ROOT / "replied").glob("*.json")
    }
    inbox_paths = []
    for bucket in ("reviewed", "closed"):
        inbox_paths.extend(sorted((INBOX_ROOT / bucket).rglob("*.json")))
    for path in inbox_paths:
        payload = load_json(path, {})
        if str(path) in already_reconciled_sources or not is_qualified_inbound(payload):
            continue
        _, sender_email = parseaddr(str(payload.get("from") or payload.get("sender") or ""))
        sender_email = sender_email.lower().strip()
        candidates = outbound_candidates(sender_email, str(payload.get("subject") or ""))
        if not candidates:
            skipped.append({"source": str(path), "sender": sender_email, "reason": "no_matching_sent_packet"})
            continue
        outbound_path, outbound = candidates[0]
        destinations = move_sidecars(outbound_path.stem, path, payload, dry_run=dry_run)
        lead_updated = mark_lead_replied(outbound.get("lead_id"), dry_run=dry_run)
        matched.append(
            {
                "source": str(path),
                "sender": sender_email,
                "subject": payload.get("subject") or "",
                "outbound_stem": outbound_path.stem,
                "company_name": outbound.get("company_name") or "",
                "lead_id": outbound.get("lead_id"),
                "lead_updated": lead_updated,
                "destinations": destinations,
            }
        )
    report = {
        "generated_at": utc_now(),
        "ok": True,
        "dry_run": dry_run,
        "matched_count": len(matched),
        "skipped_count": len(skipped),
        "matched": matched,
        "skipped_sample": skipped[:20],
        "guardrail": "Internal queue-state reconciliation only. No email is sent, drafted, approved, or deleted.",
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Reply Reconciliation",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Dry run: `{dry_run}`",
        f"- Matched: `{report['matched_count']}`",
        f"- Skipped: `{report['skipped_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "## Matches",
        "",
    ]
    lines.extend(
        f"- `{item['outbound_stem']}` -> replied from `{item['sender']}` ({item['subject']})"
        for item in matched
    )
    if not matched:
        lines.append("- No unreconciled qualified replies.")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile qualified inbound replies with sent outreach packets.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(reconcile(dry_run=args.dry_run), indent=2))
