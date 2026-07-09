#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import ssl
import subprocess
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
INBOX_ROOT = ROOT / "outreach" / "inbox"
INBOX_NEW = ROOT / "outreach" / "inbox" / "new"
INBOX_REVIEWED = ROOT / "outreach" / "inbox" / "reviewed"
STATE_DIR = ROOT / "ops" / "agent-control" / "state" / "operator-notifier"
OPPORTUNITY_MANAGER_STATE = ROOT / "ops" / "agent-control" / "state" / "latest-opportunity-manager.json"
LATEST_JSON = STATE_DIR / "latest-alerts.json"
LATEST_MD = STATE_DIR / "latest-alerts.md"
SEEN_JSON = STATE_DIR / "seen-alerts.json"
FORWARDED_JSON = STATE_DIR / "forwarded-alerts.json"
OUTREACH_ENV = ROOT / "outreach" / ".env.local"
DEFAULT_FORWARD_TO = "chandruvasu@icloud.com"

POSITIVE_TERMS = {
    "ok",
    "yes",
    "sure",
    "interested",
    "send",
    "demo",
    "call",
    "meeting",
    "schedule",
    "available",
    "let's",
    "lets",
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


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def clean_text(value: object, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def sender_domain_from_email(email: str) -> str:
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].lower().strip()


def is_system_sender(email: str) -> bool:
    value = email.lower()
    domain = sender_domain_from_email(value)
    return any(term in value or term in domain for term in SYSTEM_SENDER_TERMS)


def classify_alert(payload: dict[str, Any], path: Path) -> dict[str, Any] | None:
    response_status = str(payload.get("response_status") or "").strip().lower()
    if response_status in {"sent", "closed", "resolved"}:
        return None

    bucket = str(payload.get("triage_bucket") or "").lower()
    priority = str(payload.get("triage_priority") or "").lower()
    action = str(payload.get("triage_action") or "").lower()
    subject = str(payload.get("subject") or "")
    snippet = str(payload.get("snippet") or "")
    sender_name, sender_email = parseaddr(str(payload.get("from") or ""))
    sender_email = sender_email or str(payload.get("sender_email") or "")
    if is_system_sender(sender_email):
        return None

    if bucket != "direct" and priority != "high" and action != "review":
        return None

    normalized = re.sub(r"[^a-z0-9']+", " ", f"{subject} {snippet}".lower())
    terms = set(normalized.split())
    positive_hits = sorted(POSITIVE_TERMS & terms)
    needs_demo = any(term in terms for term in {"demo", "call", "meeting", "schedule"})

    severity = "high" if positive_hits or needs_demo else "review"
    reason = "positive reply detected" if positive_hits else "direct business inbound needs review"
    if needs_demo:
        reason = "demo or meeting language detected"

    return {
        "id": path.stem,
        "severity": severity,
        "reason": reason,
        "positive_hits": positive_hits,
        "needs_operator": True,
        "needs_demo_followup": needs_demo,
        "from": payload.get("from") or "",
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": subject,
        "snippet": clean_text(snippet),
        "captured_at": payload.get("captured_at") or "",
        "path": str(path),
        "eml_path": str(path.with_suffix(".eml")),
    }


def active_alerts() -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    source_paths: set[str] = set()
    for inbox_state, root in (("new", INBOX_NEW), ("reviewed", INBOX_REVIEWED)):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.json")):
            payload = load_json(path, {})
            if not isinstance(payload, dict):
                continue
            alert = classify_alert(payload, path)
            if alert:
                alert["inbox_state"] = inbox_state
                alerts.append(alert)
                source_paths.add(str(path))
    alerts.extend(active_opportunity_alerts(source_paths))
    return alerts


def active_opportunity_alerts(skip_source_paths: set[str]) -> list[dict[str, Any]]:
    payload = load_json(OPPORTUNITY_MANAGER_STATE, {})
    if not isinstance(payload, dict):
        return []
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    alerts: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("active"):
            continue
        if item.get("source") and str(item.get("source")) in skip_source_paths:
            continue
        if item.get("stage") not in {"inbound-hit-needs-review", "reply-needs-response", "proposal-needed", "pilot-discovery-needed"}:
            continue
        alerts.append(
            {
                "id": f"opportunity-{item.get('id')}",
                "severity": "high",
                "reason": "active opportunity needs operator review",
                "positive_hits": [],
                "needs_operator": True,
                "needs_demo_followup": item.get("service_slug") == "ai-voice-intake",
                "from": item.get("source_from") or item.get("contact_email") or "",
                "sender_name": item.get("account_name") or "",
                "sender_email": item.get("contact_email") or "",
                "subject": item.get("source_subject") or f"Opportunity: {item.get('account_name')}",
                "snippet": clean_text(item.get("notes") or item.get("source_snippet") or item.get("next_action") or ""),
                "captured_at": item.get("updated_at") or item.get("created_at") or "",
                "path": item.get("source") or str(OPPORTUNITY_MANAGER_STATE),
                "eml_path": "",
                "inbox_state": "opportunity",
                "next_action": item.get("next_action") or "",
            }
        )
    return alerts


def write_markdown(alerts: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# JVT Operator Alerts",
        "",
        f"Generated: {utc_now()}",
        f"Active alerts: {len(alerts)}",
        "",
    ]
    if not alerts:
        lines.append("No active operator alerts.")
    for alert in alerts:
        lines.extend(
            [
                f"## {alert['severity'].upper()}: {alert['subject']}",
                "",
                f"- From: {alert['from']}",
                f"- Reason: {alert['reason']}",
                f"- Positive hits: {', '.join(alert['positive_hits']) or 'none'}",
                f"- Needs demo follow-up: {alert['needs_demo_followup']}",
                f"- Source: {alert['path']}",
                "",
                alert["snippet"],
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def notify_local(alert: dict[str, Any]) -> None:
    if os.environ.get("JVT_OPERATOR_NOTIFIER_OSASCRIPT", "1").lower() not in {"1", "true", "yes", "on"}:
        return
    title = "JVT prospect reply"
    message = f"{alert.get('sender_name') or alert.get('sender_email')}: {alert.get('snippet')}"
    message = clean_text(message, 180).replace('"', "'")
    title = title.replace('"', "'")
    subprocess.run(
        ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def smtp_required_values() -> dict[str, str]:
    return {
        "SMTP_HOST": os.environ.get("SMTP_HOST", "").strip(),
        "SMTP_PORT": os.environ.get("SMTP_PORT", "587").strip(),
        "SMTP_USERNAME": os.environ.get("SMTP_USERNAME", "").strip(),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", "").strip(),
    }


def smtp_ready() -> bool:
    values = smtp_required_values()
    return bool(values["SMTP_HOST"] and values["SMTP_USERNAME"] and values["SMTP_PASSWORD"])


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def alert_email_body(alert: dict[str, Any]) -> str:
    return "\n".join(
        [
            "JVT has a prospect reply that needs attention.",
            "",
            f"Severity: {alert.get('severity')}",
            f"Reason: {alert.get('reason')}",
            f"From: {alert.get('from')}",
            f"Subject: {alert.get('subject')}",
            f"Captured: {alert.get('captured_at')}",
            f"Needs demo follow-up: {alert.get('needs_demo_followup')}",
            "",
            "Snippet:",
            str(alert.get("snippet") or ""),
            "",
            "Source files on the M4:",
            str(alert.get("path") or ""),
            str(alert.get("eml_path") or ""),
            "",
            "This is an internal JVT operator alert. Review before replying.",
        ]
    )


def forward_alert_email(alert: dict[str, Any]) -> bool:
    if not smtp_ready():
        return False

    forward_to = os.environ.get("JVT_OPERATOR_ALERT_FORWARD_TO", DEFAULT_FORWARD_TO).strip() or DEFAULT_FORWARD_TO
    from_email = os.environ.get("JVT_FROM_EMAIL", "hello@jvt-technologies.com").strip()
    from_name = os.environ.get("JVT_FROM_NAME", "JVT Technologies").strip()
    subject = f"JVT hit: {alert.get('sender_name') or alert.get('sender_email') or 'Prospect reply'}"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = forward_to
    message["Reply-To"] = from_email
    message.set_content(alert_email_body(alert))

    values = smtp_required_values()
    port = int(values["SMTP_PORT"] or "587")
    use_ssl = bool_env("SMTP_USE_SSL", port == 465)
    use_starttls = bool_env("SMTP_USE_STARTTLS", not use_ssl)
    if use_ssl:
        with smtplib.SMTP_SSL(values["SMTP_HOST"], port, context=ssl.create_default_context(), timeout=30) as server:
            server.login(values["SMTP_USERNAME"], values["SMTP_PASSWORD"])
            server.send_message(message)
    else:
        with smtplib.SMTP(values["SMTP_HOST"], port, timeout=30) as server:
            server.ehlo()
            if use_starttls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(values["SMTP_USERNAME"], values["SMTP_PASSWORD"])
            server.send_message(message)
    return True


def main() -> None:
    load_env_file(OUTREACH_ENV)
    parser = argparse.ArgumentParser(description="Detect JVT replies that need operator attention.")
    parser.add_argument("--notify", action="store_true", help="Raise a local desktop notification for new alerts.")
    parser.add_argument("--forward", action="store_true", help="Forward new alert summaries to the operator email.")
    args = parser.parse_args()

    alerts = active_alerts()
    seen = set(load_json(SEEN_JSON, []))
    forwarded = set(load_json(FORWARDED_JSON, []))
    current_ids = {str(alert["id"]) for alert in alerts}
    new_alerts = [alert for alert in alerts if str(alert["id"]) not in seen]
    forward_candidates = [alert for alert in alerts if str(alert["id"]) not in forwarded]
    forward_errors: list[dict[str, str]] = []
    forwarded_sent = 0

    if args.notify:
        for alert in new_alerts:
            notify_local(alert)

    if args.forward or bool_env("JVT_OPERATOR_ALERT_FORWARD_ENABLED", True):
        for alert in forward_candidates:
            try:
                if forward_alert_email(alert):
                    forwarded.add(str(alert["id"]))
                    forwarded_sent += 1
            except Exception as exc:
                forward_errors.append({"id": str(alert.get("id") or ""), "error": str(exc)})

    write_json(
        LATEST_JSON,
        {
            "generated_at": utc_now(),
            "active_count": len(alerts),
            "new_count": len(new_alerts),
            "forwarded_count": forwarded_sent,
            "forward_errors": forward_errors,
            "scan_scopes": ["inbox/new", "inbox/reviewed", "active opportunities"],
            "alerts": alerts,
        },
    )
    write_markdown(alerts, LATEST_MD)
    write_json(SEEN_JSON, sorted(seen | current_ids))
    write_json(FORWARDED_JSON, sorted(forwarded))
    print(json.dumps({"active": len(alerts), "new": len(new_alerts), "forward_errors": len(forward_errors), "latest": str(LATEST_JSON)}))


if __name__ == "__main__":
    main()
