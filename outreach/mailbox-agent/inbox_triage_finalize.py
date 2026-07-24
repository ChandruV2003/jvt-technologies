#!/usr/bin/env python3

from __future__ import annotations

import argparse
import email
import importlib.util
import json
import os
import re
import shutil
from datetime import datetime, timezone
from email import policy
from email.utils import parseaddr
from pathlib import Path
from typing import Any


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
INBOX_ROOT = ROOT / "outreach" / "inbox"
INBOX_NEW = INBOX_ROOT / "new"
INBOX_REVIEWED = INBOX_ROOT / "reviewed"
INBOX_CLOSED = INBOX_ROOT / "closed"
STATE_ROOT = ROOT / "ops" / "agent-control" / "state"
LATEST_JSON = STATE_ROOT / "latest-inbox-triage-finalizer.json"
LATEST_MD = STATE_ROOT / "latest-inbox-triage-finalizer.md"
MAILBOX_LISTENER = ROOT / "outreach" / "mailbox-agent" / "mailbox_listener.py"

DEFAULT_OPERATOR_EMAILS = {
    "chandruvasu@icloud.com",
    "chandruv@jvt-technologies.com",
    "hello@jvt-technologies.com",
    "jvtvasu@icloud.com",
}

NOISE_SUBJECT_MARKERS = {
    "tax-optimization checklist",
    "newsletter",
    "webinar",
    "limited time",
    "special offer",
    "sale",
    "discount",
}

NOISE_BODY_MARKERS = {
    "unsubscribe",
    "view this email as a web page",
    "manage your preferences",
    "you are receiving this email because",
    "email marketing",
    "convertkit",
    "mailchimp",
    "constant contact",
}

SYSTEM_SENDER_TERMS = {
    "no-reply",
    "noreply",
    "donotreply",
    "mailer-daemon",
    "postmaster",
    "notification",
    "newsletter",
    "bankofamerica",
    "google",
    "microsoft",
    "apple",
    "cloudflare",
    "github",
    "stripe",
    "alpaca",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_mailbox_listener() -> Any:
    spec = importlib.util.spec_from_file_location("jvt_mailbox_listener", MAILBOX_LISTENER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load mailbox listener from {MAILBOX_LISTENER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def operator_emails() -> set[str]:
    raw = os.environ.get("JVT_OPERATOR_EMAILS", "")
    configured = {value.strip().lower() for value in raw.split(",") if value.strip()}
    return configured or DEFAULT_OPERATOR_EMAILS


def sender_domain(email_address: str) -> str:
    if "@" not in email_address:
        return ""
    return email_address.rsplit("@", 1)[-1].lower().strip()


def is_system_sender(email_address: str) -> bool:
    value = email_address.lower()
    domain = sender_domain(value)
    return any(term in value or term in domain for term in SYSTEM_SENDER_TERMS)


def text_from_eml(path: Path, listener: Any) -> str:
    eml_path = path.with_suffix(".eml")
    if not eml_path.exists():
        return ""
    try:
        message = email.message_from_bytes(eml_path.read_bytes(), policy=policy.default)
        return str(listener.extract_text_part(message) or "").strip()
    except Exception:
        return ""


def compact(value: Any, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def date_folder_for(path: Path, payload: dict[str, Any]) -> str:
    if re.match(r"^\d{4}-\d{2}-\d{2}$", path.parent.name):
        return path.parent.name
    captured = str(payload.get("captured_at") or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}", captured):
        return captured[:10]
    return datetime.now(timezone.utc).date().isoformat()


def classify_item(path: Path, listener: Any) -> dict[str, Any]:
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        payload = {}
    subject = str(payload.get("subject") or "")
    sender_raw = str(payload.get("from") or payload.get("sender") or "")
    to_raw = str(payload.get("to") or payload.get("recipient_email") or "")
    sender_name, sender_email = parseaddr(sender_raw)
    sender_email = sender_email.lower().strip()
    body_text = text_from_eml(path, listener) or str(payload.get("snippet") or "")
    subject_l = subject.lower()
    body_l = body_text.lower()

    listener_triage = listener.classify_message(subject, sender_raw, to_raw, body_text)
    listener_bucket = str(listener_triage.get("triage_bucket") or "").lower()
    listener_priority = str(listener_triage.get("triage_priority") or "").lower()
    listener_action = str(listener_triage.get("triage_action") or "").lower()

    reasons: list[str] = []
    target = "reviewed"
    agent_status = "reviewed"
    needs_reply_draft = False
    next_action = "Review and decide whether a human reply draft is needed."

    if sender_email in operator_emails() or sender_email.endswith("@jvt-technologies.com"):
        reasons.append("operator_or_internal_sender")
        agent_status = "reviewed_internal"
        next_action = "Keep as internal context. Do not include in external follow-up automation."
    elif is_system_sender(sender_email):
        target = "closed"
        agent_status = "closed_system_sender"
        reasons.append("system_sender")
        next_action = "No operator action needed."
    elif any(marker in subject_l for marker in NOISE_SUBJECT_MARKERS) or any(marker in body_l for marker in NOISE_BODY_MARKERS):
        target = "closed"
        agent_status = "closed_promotional_or_newsletter"
        reasons.append("promotional_or_newsletter_marker")
        next_action = "No operator action needed."
    elif listener_bucket in {"promotional", "system", "auto-reply", "personal"} and listener_priority == "low" and listener_action in {"ignore", "defer"}:
        target = "closed"
        agent_status = f"closed_{listener_bucket}"
        reasons.append(f"listener_low_priority_{listener_bucket}")
        next_action = "No operator action needed."
    elif listener_bucket == "direct" or listener_priority == "high" or listener_action == "review":
        reasons.append("direct_or_high_priority_inbound")
        needs_reply_draft = bool(compact(body_text, 40))
        next_action = "Keep visible for operator review; generate or review a reply draft before any response."
    else:
        reasons.append("ambiguous_inbound")
        next_action = "Keep visible for operator review because classification was ambiguous."

    return {
        "source_path": str(path),
        "target": target,
        "agent_triage_status": agent_status,
        "agent_triage_reason": ", ".join(reasons),
        "agent_next_action": next_action,
        "needs_reply_draft": needs_reply_draft,
        "subject": subject,
        "from": sender_raw,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "listener_triage": listener_triage,
        "body_preview": compact(body_text),
        "payload": payload,
    }


def move_item(path: Path, target: str, payload: dict[str, Any], dry_run: bool) -> dict[str, str]:
    target_root = INBOX_REVIEWED if target == "reviewed" else INBOX_CLOSED
    target_dir = target_root / date_folder_for(path, payload)
    destination_json = target_dir / path.name
    destination_eml = target_dir / path.with_suffix(".eml").name
    if dry_run:
        return {"json": str(destination_json), "eml": str(destination_eml), "dry_run": "true"}

    target_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    shutil.move(str(path), str(destination_json))
    source_eml = path.with_suffix(".eml")
    if source_eml.exists():
        shutil.move(str(source_eml), str(destination_eml))
    return {"json": str(destination_json), "eml": str(destination_eml)}


def finalize(limit: int, dry_run: bool) -> dict[str, Any]:
    listener = load_mailbox_listener()
    paths = sorted(INBOX_NEW.rglob("*.json"))[:limit] if INBOX_NEW.exists() else []
    results: list[dict[str, Any]] = []
    moved = {"reviewed": 0, "closed": 0}
    for path in paths:
        item = classify_item(path, listener)
        payload = dict(item.pop("payload"))
        payload.update({
            "status": item["target"],
            "agent_triage_status": item["agent_triage_status"],
            "agent_triage_reason": item["agent_triage_reason"],
            "agent_triage_reviewed_at": utc_now(),
            "agent_next_action": item["agent_next_action"],
            "agent_needs_reply_draft": item["needs_reply_draft"],
            "agent_listener_triage": item["listener_triage"],
        })
        destinations = move_item(path, str(item["target"]), payload, dry_run)
        moved[str(item["target"])] = moved.get(str(item["target"]), 0) + 1
        results.append({**item, "destinations": destinations})

    report = {
        "generated_at": utc_now(),
        "ok": True,
        "dry_run": dry_run,
        "processed_count": len(results),
        "moved_counts": moved,
        "guardrail": "Internal inbox state triage only. No replies, outbound sends, provider calls, spending, financial actions, public posts, or external commitments.",
        "results": results,
    }
    write_json(LATEST_JSON, report)
    write_markdown(report, LATEST_MD)
    return report


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Inbox Triage Finalizer",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Dry run: `{report['dry_run']}`",
        f"- Processed: `{report['processed_count']}`",
        f"- Moved to reviewed: `{report['moved_counts'].get('reviewed', 0)}`",
        f"- Moved to closed: `{report['moved_counts'].get('closed', 0)}`",
        f"- Guardrail: {report['guardrail']}",
        "",
    ]
    for index, item in enumerate(report.get("results", []), start=1):
        lines.extend([
            f"## {index}. {item.get('subject') or item.get('source_path')}",
            "",
            f"- From: {item.get('from') or ''}",
            f"- Source: `{Path(str(item.get('source_path'))).relative_to(ROOT)}`",
            f"- Target: `{item.get('target')}`",
            f"- Agent status: `{item.get('agent_triage_status')}`",
            f"- Reason: {item.get('agent_triage_reason')}",
            f"- Needs reply draft: `{item.get('needs_reply_draft')}`",
            f"- Next: {item.get('agent_next_action')}",
            f"- Destination: `{item.get('destinations', {}).get('json', '')}`",
            "",
            "Preview:",
            "",
            f"> {item.get('body_preview') or '(empty)'}",
            "",
        ])
    if not report.get("results"):
        lines.append("No untriaged inbox items were present.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize safe JVT inbox triage from raw new items into reviewed or closed.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = finalize(max(1, args.limit), args.dry_run)
    print(json.dumps({
        "ok": report["ok"],
        "processed_count": report["processed_count"],
        "moved_counts": report["moved_counts"],
        "dry_run": report["dry_run"],
        "latest": str(LATEST_JSON),
    }, indent=2))


if __name__ == "__main__":
    main()
