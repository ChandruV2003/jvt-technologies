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
from email.utils import parseaddr
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


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


def classify_message(subject: str, sender: str, recipient: str, text_body: str) -> dict[str, str]:
    sender_addr = parseaddr(sender)[1].lower().strip()
    recipient_addr = parseaddr(recipient)[1].lower().strip() or recipient.lower().strip()
    sender_domain = sender_addr.split("@", 1)[1] if "@" in sender_addr else ""
    subject_l = subject.lower()
    snippet_l = text_body.lower()

    reasons: list[str] = []

    if recipient_addr.endswith("@jvt-technologies.com"):
        reasons.append("sent_to_jvt_domain")
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
    )
    promo_domains = ("mailchimp", "sfmc", "messagegears", "constantcontact", "hubspot")
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

    if sender_domain in {"email.apple.com", "apple.com"} or re.search(r"\b(alert|receipt|verification|invoice)\b", subject_l):
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

    return {
        "sender_email": sender_addr,
        "sender_domain": sender_domain,
        "recipient_email": recipient_addr,
        "triage_bucket": "review",
        "triage_priority": "medium",
        "triage_action": "review",
        "triage_reason": "default_review",
    }


def write_message(output_dir: Path, uid: int, raw_bytes: bytes) -> tuple[Path, Path]:
    message = email.message_from_bytes(raw_bytes, policy=policy.default)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    day_dir = output_dir / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    subject = decode_header_value(message.get("Subject"))
    sender = decode_header_value(message.get("From"))
    recipient = decode_header_value(message.get("To"))
    entry_slug = f"{stamp}-uid-{uid}"
    eml_path = day_dir / f"{entry_slug}.eml"
    json_path = day_dir / f"{entry_slug}.json"

    text_body = extract_text_part(message).strip()
    triage = classify_message(subject, sender, recipient, text_body)
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
                "status": "new",
                **triage,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    eml_path.write_bytes(raw_bytes)
    return json_path, eml_path


def fetch_new_messages(client: imaplib.IMAP4_SSL, last_uid: int, max_per_run: int) -> list[tuple[int, bytes]]:
    status, data = client.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    if status != "OK":
        raise RuntimeError("Unable to search mailbox for new messages")
    uids = [int(uid) for uid in data[0].split() if uid.strip()]
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


def run_once(host: str, port: int, username: str, password: str, folder: str, output_dir: Path, state_file: Path, max_per_run: int) -> int:
    state = load_state(state_file)
    last_uid = int(state.get("last_uid", 0))

    with imaplib.IMAP4_SSL(host, port) as client:
        client.login(username, password)
        status, _ = client.select(folder)
        if status != "OK":
            raise RuntimeError(f"Unable to select mailbox folder {folder}")

        messages = fetch_new_messages(client, last_uid=last_uid, max_per_run=max_per_run)
        newest_uid = last_uid
        for uid, raw_bytes in messages:
            write_message(output_dir, uid, raw_bytes)
            newest_uid = max(newest_uid, uid)
        save_state(state_file, newest_uid)
        return len(messages)


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
        )
        print(f"Imported {count} message(s).")
        return

    while True:
        count = run_once(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            folder=args.folder,
            output_dir=args.output_dir,
            state_file=args.state_file,
            max_per_run=args.max_per_run,
        )
        print(f"[{datetime.now().isoformat(timespec='seconds')}] Imported {count} message(s).")
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
