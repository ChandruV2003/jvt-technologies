#!/usr/bin/env python3

from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import re
import time
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.utils import getaddresses, parseaddr
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_list(name: str, default: str = "") -> set[str]:
    raw_value = os.environ.get(name, default)
    return {
        value.strip().lower()
        for value in raw_value.split(",")
        if value.strip()
    }


def load_state(path: Path) -> dict[str, int]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"last_uid": 0}


def save_state(path: Path, last_uid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_uid": last_uid}, indent=2) + "\n", encoding="utf-8")


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    decoded = email.header.decode_header(value)
    parts: list[str] = []
    for chunk, encoding in decoded:
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def extract_text_part(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            if disposition == "attachment":
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    payload = message.get_payload(decode=True) or b""
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def recipient_addresses(message: Message) -> set[str]:
    headers = [
        "To",
        "Cc",
        "Delivered-To",
        "Envelope-To",
        "X-Original-To",
        "Apparently-To",
    ]
    values: list[str] = []
    for header in headers:
        values.extend(message.get_all(header, []))
    return {
        address.lower().strip()
        for _, address in getaddresses(values)
        if address
    }


def should_monitor_message(message: Message, monitored_recipients: set[str]) -> bool:
    if not monitored_recipients:
        return True
    return bool(recipient_addresses(message) & monitored_recipients)


def is_auto_reply(subject_l: str, snippet_l: str) -> bool:
    auto_reply_markers = (
        "out of office",
        "out-of-office",
        "automatic reply",
        "auto reply",
        "autoreply",
        "away from the office",
        "currently away",
        "i am away",
        "i'm away",
        "limited e-mail access",
        "limited email access",
        "on vacation",
    )
    return any(marker in subject_l or marker in snippet_l for marker in auto_reply_markers)


def classify_message(subject: str, sender: str, recipient: str, text_body: str) -> dict[str, str]:
    sender_addr = parseaddr(sender)[1].lower().strip()
    recipient_addr = parseaddr(recipient)[1].lower().strip() or recipient.lower().strip()
    sender_domain = sender_addr.split("@", 1)[1] if "@" in sender_addr else ""
    subject_l = subject.lower()
    snippet_l = text_body.lower()

    reasons: list[str] = []

    dmarc_report_markers = (
        "dmarc aggregate report",
        "report domain:",
        "report-id:",
    )
    dmarc_sender_domains = {
        "amazonses.com",
        "google.com",
    }
    if (
        "dmarc" in subject_l
        or all(marker in subject_l for marker in ("report domain:", "submitter:"))
        or (
            sender_domain in dmarc_sender_domains
            and any(marker in subject_l for marker in dmarc_report_markers)
        )
    ):
        reasons.append("dmarc_aggregate_report")
        return {
            "sender_email": sender_addr,
            "sender_domain": sender_domain,
            "recipient_email": recipient_addr,
            "triage_bucket": "system",
            "triage_priority": "low",
            "triage_action": "defer",
            "triage_reason": ", ".join(reasons),
        }

    if recipient_addr.endswith("@jvt-technologies.com"):
        reasons.append("sent_to_jvt_domain")
        if is_auto_reply(subject_l, snippet_l):
            reasons.append("out_of_office_auto_reply")
            return {
                "sender_email": sender_addr,
                "sender_domain": sender_domain,
                "recipient_email": recipient_addr,
                "triage_bucket": "auto-reply",
                "triage_priority": "low",
                "triage_action": "defer",
                "triage_reason": ", ".join(reasons),
            }

        if sender_addr.endswith("@jvt-technologies.com"):
            reasons.append("internal_sender")
            return {
                "sender_email": sender_addr,
                "sender_domain": sender_domain,
                "recipient_email": recipient_addr,
                "triage_bucket": "internal-test",
                "triage_priority": "low",
                "triage_action": "ignore",
                "triage_reason": ", ".join(reasons),
            }

        if any(token in sender_addr for token in ("noreply", "no-reply", "do-not-reply")):
            reasons.append("noreply_sender")
            return {
                "sender_email": sender_addr,
                "sender_domain": sender_domain,
                "recipient_email": recipient_addr,
                "triage_bucket": "system",
                "triage_priority": "low",
                "triage_action": "defer",
                "triage_reason": ", ".join(reasons),
            }

        reasons.append("direct_business_inbound")
        return {
            "sender_email": sender_addr,
            "sender_domain": sender_domain,
            "recipient_email": recipient_addr,
            "triage_bucket": "direct",
            "triage_priority": "high",
            "triage_action": "review",
            "triage_reason": ", ".join(reasons),
        }

    promo_markers = (
        "unsubscribe",
        "view this email as a web page",
        "save on your next visit",
        "special offer",
        "% off",
        "limited time",
        "newsletter",
        "sale",
        "order delivered",
        "survey",
        "please share your thoughts",
    )
    promo_domains = (
        "mailchimp",
        "sfmc",
        "messagegears",
        "constantcontact",
        "hubspot",
        "sailthru",
        "beehiiv",
        "newsletter",
        "service.alibaba.com",
        "mg.homedepot.com",
        "qemailserver.com",
    )
    if any(marker in snippet_l or marker in subject_l for marker in promo_markers) or any(domain in sender_domain for domain in promo_domains):
        reasons.append("promotional_markers")
        return {
            "sender_email": sender_addr,
            "sender_domain": sender_domain,
            "recipient_email": recipient_addr,
            "triage_bucket": "promotional",
            "triage_priority": "low",
            "triage_action": "ignore",
            "triage_reason": ", ".join(reasons),
        }

    service_markers = (
        "verification",
        "verify your email",
        "security",
        "oauth",
        "password",
        "receipt",
        "invoice",
        "bank",
        "card",
        "venmo",
        "github",
        "postman",
        "application was approved",
        "account application",
        "touch id",
        "face id",
        "run failed",
    )
    if sender_domain in {"email.apple.com", "apple.com"} or any(marker in subject_l or marker in sender_domain for marker in service_markers):
        reasons.append("system_or_service_mail")
        return {
            "sender_email": sender_addr,
            "sender_domain": sender_domain,
            "recipient_email": recipient_addr,
            "triage_bucket": "system",
            "triage_priority": "low",
            "triage_action": "defer",
            "triage_reason": ", ".join(reasons),
        }

    reasons.append("personal_or_unmatched_non_business_inbound")
    return {
        "sender_email": sender_addr,
        "sender_domain": sender_domain,
        "recipient_email": recipient_addr,
        "triage_bucket": "personal",
        "triage_priority": "low",
        "triage_action": "defer",
        "triage_reason": ", ".join(reasons),
    }


def status_for_triage(triage: dict[str, str]) -> str:
    low_priority = triage.get("triage_priority") == "low"
    action = triage.get("triage_action")
    if low_priority and action in {"defer", "ignore"}:
        return "closed"
    return "new"


def write_message(output_dir: Path, uid: int, raw_bytes: bytes, monitored_recipients: set[str]) -> tuple[Path, Path] | None:
    message = email.message_from_bytes(raw_bytes, policy=policy.default)
    if not should_monitor_message(message, monitored_recipients):
        return None

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    subject = decode_header_value(message.get("Subject"))
    sender = decode_header_value(message.get("From"))
    recipient = decode_header_value(message.get("To"))
    text_body = extract_text_part(message).strip()
    triage = classify_message(subject, sender, recipient, text_body)
    status = status_for_triage(triage)

    target_root = output_dir
    if status == "closed" and output_dir.name == "new":
        target_root = output_dir.parent / "closed"
    day_dir = target_root / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    entry_slug = f"{stamp}-uid-{uid}"
    eml_path = day_dir / f"{entry_slug}.eml"
    json_path = day_dir / f"{entry_slug}.json"

    json_path.write_text(
        json.dumps(
            {
                "uid": uid,
                "captured_at": now.isoformat(),
                "subject": subject,
                "from": sender,
                "to": recipient,
                "date": decode_header_value(message.get("Date")),
                "message_id": decode_header_value(message.get("Message-ID")),
                "snippet": text_body[:600],
                "status": status,
                **triage,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    eml_path.write_bytes(raw_bytes)
    return json_path, eml_path


def parse_search_uids(data: list[bytes | None] | tuple[bytes | None, ...] | None) -> list[int]:
    if not data:
        return []

    first = data[0]
    if not first:
        return []

    if isinstance(first, bytes):
        raw_uids = first.split()
    else:
        raw_uids = str(first).encode("utf-8", errors="ignore").split()

    parsed: list[int] = []
    for uid in raw_uids:
        try:
            parsed.append(int(uid))
        except (TypeError, ValueError):
            continue
    return parsed


def fetch_new_messages(client: imaplib.IMAP4_SSL, last_uid: int, max_per_run: int) -> list[tuple[int, bytes]]:
    status, data = client.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    if status != "OK":
        raise RuntimeError("Unable to search mailbox for new messages")
    uids = parse_search_uids(data)
    selected = uids[:max_per_run]
    messages: list[tuple[int, bytes]] = []
    for uid in selected:
        status, fetched = client.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if status != "OK":
            continue
        for part in fetched:
            if isinstance(part, tuple):
                messages.append((uid, part[1]))
                break
    return messages


def run_once(
    host: str,
    port: int,
    username: str,
    password: str,
    folder: str,
    output_dir: Path,
    state_file: Path,
    max_per_run: int,
    monitored_recipients: set[str],
    timeout_seconds: float,
) -> int:
    state = load_state(state_file)
    last_uid = int(state.get("last_uid", 0))

    with imaplib.IMAP4_SSL(host, port, timeout=timeout_seconds) as client:
        client.login(username, password)
        status, _ = client.select(folder)
        if status != "OK":
            raise RuntimeError(f"Unable to select mailbox folder {folder}")

        messages = fetch_new_messages(client, last_uid=last_uid, max_per_run=max_per_run)
        newest_uid = last_uid
        imported_count = 0
        for uid, raw_bytes in messages:
            imported = write_message(output_dir, uid, raw_bytes, monitored_recipients)
            if imported:
                imported_count += 1
            newest_uid = max(newest_uid, uid)
        save_state(state_file, newest_uid)
        return imported_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative IMAP inbox listener for JVT Technologies")
    parser.add_argument("--host", default=env("IMAP_HOST"))
    parser.add_argument("--port", type=int, default=int(env("IMAP_PORT", "993")))
    parser.add_argument("--username", default=env("IMAP_USERNAME"))
    parser.add_argument("--password", default=env("IMAP_PASSWORD"))
    parser.add_argument("--folder", default=env("IMAP_FOLDER", "INBOX"))
    parser.add_argument("--output-dir", type=Path, default=Path(env("INBOX_OUTPUT_DIR")))
    parser.add_argument("--state-file", type=Path, default=Path(env("STATE_FILE")))
    parser.add_argument("--poll-seconds", type=int, default=int(env("MAILBOX_POLL_SECONDS", "180")))
    parser.add_argument("--max-per-run", type=int, default=int(env("MAILBOX_MAX_PER_RUN", "10")))
    parser.add_argument("--imap-timeout-seconds", type=float, default=float(env("MAILBOX_IMAP_TIMEOUT_SECONDS", "30")))
    parser.add_argument(
        "--monitored-recipients",
        default=env("MONITORED_RECIPIENTS", "hello@jvt-technologies.com,chandruv@jvt-technologies.com"),
        help="Comma-separated recipient addresses to import. Other mailbox messages are ignored.",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    required = {
        "host": args.host,
        "username": args.username,
        "password": args.password,
        "output_dir": str(args.output_dir),
        "state_file": str(args.state_file),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(f"Missing required configuration: {', '.join(missing)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.state_file.parent.mkdir(parents=True, exist_ok=True)
    monitored_recipients = {
        value.strip().lower()
        for value in args.monitored_recipients.split(",")
        if value.strip()
    }

    if args.once:
        count = run_once(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            folder=args.folder,
            output_dir=args.output_dir,
            state_file=args.state_file,
            max_per_run=args.max_per_run,
            monitored_recipients=monitored_recipients,
            timeout_seconds=args.imap_timeout_seconds,
        )
        print(f"Imported {count} message(s).")
        return

    while True:
        try:
            count = run_once(
                host=args.host,
                port=args.port,
                username=args.username,
                password=args.password,
                folder=args.folder,
                output_dir=args.output_dir,
                state_file=args.state_file,
                max_per_run=args.max_per_run,
                monitored_recipients=monitored_recipients,
                timeout_seconds=args.imap_timeout_seconds,
            )
            print(f"[{datetime.now().isoformat(timespec='seconds')}] Imported {count} message(s).", flush=True)
        except Exception as exc:
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] Mailbox listener error: {type(exc).__name__}: {exc}",
                flush=True,
            )
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
