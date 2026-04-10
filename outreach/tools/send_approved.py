#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach")
QUEUE_ROOT = ROOT / "queue"
APPROVED_DIR = QUEUE_ROOT / "approved"
SENT_DIR = QUEUE_ROOT / "sent"
DEFAULT_DB = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/lead-pipeline/data/jvt_leads.sqlite3")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def packet_bundle(stem: str) -> dict[str, Path]:
    bundle: dict[str, Path] = {}
    for suffix in (".json", ".txt", ".html", ".md"):
        path = APPROVED_DIR / f"{stem}{suffix}"
        if path.exists():
            bundle[suffix] = path
    if ".json" not in bundle:
        raise SystemExit(f"Approved packet {stem} is missing its .json metadata file")
    if ".txt" not in bundle:
        raise SystemExit(f"Approved packet {stem} is missing its .txt body")
    return bundle


def approved_stems() -> list[str]:
    return sorted(path.stem for path in APPROVED_DIR.glob("*.json"))


def sent_today_count() -> int:
    today = datetime.now().date().isoformat()
    return len(list(SENT_DIR.glob(f"{today}-*.json")))


def resolve_recipient(metadata: dict[str, object], db_path: Path) -> str:
    recipient = str(metadata.get("recipient_email") or "").strip()
    if recipient:
        return recipient

    lead_id = metadata.get("lead_id")
    if not lead_id:
        raise SystemExit("Packet metadata has no recipient_email or lead_id")
    if not db_path.exists():
        raise SystemExit(f"Lead DB not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT public_email FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    if row is None or not row["public_email"]:
        raise SystemExit(f"Could not resolve public_email for lead {lead_id}")
    return str(row["public_email"]).strip()


def build_message(metadata: dict[str, object], recipient_email: str, text_body: str, html_body: str | None) -> EmailMessage:
    from_name = env("JVT_FROM_NAME", "JVT Technologies")
    from_email = env("JVT_FROM_EMAIL", "hello@jvt-technologies.com")
    reply_to = env("JVT_REPLY_TO_EMAIL", from_email)
    message = EmailMessage()
    message["Subject"] = str(metadata["subject"])
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = recipient_email
    message["Reply-To"] = reply_to
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    return message


def send_via_smtp(message: EmailMessage) -> str:
    host = env("SMTP_HOST")
    port = env_int("SMTP_PORT", 587)
    username = env("SMTP_USERNAME")
    password = env("SMTP_PASSWORD")
    use_ssl = env_bool("SMTP_USE_SSL", port == 465)
    use_starttls = env_bool("SMTP_USE_STARTTLS", not use_ssl)

    missing = [name for name, value in {
        "SMTP_HOST": host,
        "SMTP_USERNAME": username,
        "SMTP_PASSWORD": password,
    }.items() if not value]
    if missing:
        raise SystemExit(f"Missing SMTP configuration: {', '.join(missing)}")

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            if use_starttls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(username, password)
            server.send_message(message)
    return message.get("Message-ID", "")


def send_via_resend(message: EmailMessage) -> str:
    api_key = env("RESEND_API_KEY")
    base_url = env("RESEND_API_BASE_URL", "https://api.resend.com")
    if not api_key:
        raise SystemExit("Missing RESEND_API_KEY")

    payload = {
        "from": message["From"],
        "to": [message["To"]],
        "subject": message["Subject"],
        "reply_to": [message["Reply-To"]],
        "text": message.get_body(preferencelist=("plain",)).get_content(),
    }
    html_part = message.get_body(preferencelist=("html",))
    if html_part:
        payload["html"] = html_part.get_content()

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            return str(body.get("id", ""))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Resend send failed: {exc.code} {detail}") from exc


def deliver(message: EmailMessage, provider: str) -> str:
    if provider == "smtp":
        return send_via_smtp(message)
    if provider == "resend":
        return send_via_resend(message)
    raise SystemExit(f"Unsupported provider: {provider}")


def archive_bundle(bundle: dict[str, Path], metadata: dict[str, object]) -> None:
    SENT_DIR.mkdir(parents=True, exist_ok=True)
    metadata["review_path"] = str(SENT_DIR / bundle[".md"].name) if ".md" in bundle else metadata.get("review_path")
    metadata["text_path"] = str(SENT_DIR / bundle[".txt"].name) if ".txt" in bundle else metadata.get("text_path")
    metadata["html_path"] = str(SENT_DIR / bundle[".html"].name) if ".html" in bundle else metadata.get("html_path")
    for suffix, path in bundle.items():
        if suffix == ".json":
            path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        destination = SENT_DIR / path.name
        path.rename(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send approved outreach packets with explicit review gating")
    parser.add_argument("--stem", action="append", help="Packet basename without extension; may be repeated")
    parser.add_argument("--all-approved", action="store_true", help="Process all approved packets up to the configured cap")
    parser.add_argument("--provider", choices=["smtp", "resend"], default=env("JVT_OUTBOUND_PROVIDER", "smtp"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--max-per-run", type=int, default=env_int("JVT_SEND_MAX_PER_RUN", 3))
    parser.add_argument("--daily-limit", type=int, default=env_int("JVT_SEND_DAILY_LIMIT", 5))
    parser.add_argument("--delay-seconds", type=int, default=env_int("JVT_SEND_DELAY_SECONDS", 5))
    parser.add_argument("--send", action="store_true", help="Actually send mail. Without this flag the script runs in dry-run mode.")
    args = parser.parse_args()

    stems = args.stem or []
    if args.all_approved:
        stems.extend(approved_stems())
    stems = list(dict.fromkeys(stems))
    if not stems:
        raise SystemExit("Provide --stem ... or use --all-approved")

    if len(stems) > args.max_per_run:
        raise SystemExit(f"Refusing to process {len(stems)} packets; max per run is {args.max_per_run}")

    if args.send and sent_today_count() + len(stems) > args.daily_limit:
        raise SystemExit(
            f"Refusing to send {len(stems)} packet(s); daily limit would be exceeded ({args.daily_limit})"
        )

    for index, stem in enumerate(stems):
        bundle = packet_bundle(stem)
        metadata = json.loads(bundle[".json"].read_text(encoding="utf-8"))
        recipient_email = resolve_recipient(metadata, args.db)
        text_body = bundle[".txt"].read_text(encoding="utf-8").strip()
        html_body = bundle[".html"].read_text(encoding="utf-8").strip() if ".html" in bundle else None
        message = build_message(metadata, recipient_email, text_body, html_body)

        if not args.send:
            print(json.dumps({
                "stem": stem,
                "mode": "dry-run",
                "provider": args.provider,
                "to": recipient_email,
                "subject": message["Subject"],
            }))
            continue

        provider_message_id = deliver(message, args.provider)
        metadata["status"] = "sent"
        metadata["sent_at"] = datetime.now().isoformat(timespec="seconds")
        metadata["provider"] = args.provider
        metadata["provider_message_id"] = provider_message_id
        metadata["recipient_email"] = recipient_email
        archive_bundle(bundle, metadata)
        print(json.dumps({
            "stem": stem,
            "mode": "sent",
            "provider": args.provider,
            "to": recipient_email,
            "subject": message["Subject"],
            "provider_message_id": provider_message_id,
        }))
        if index < len(stems) - 1:
            time.sleep(args.delay_seconds)


if __name__ == "__main__":
    main()
