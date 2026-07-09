#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python fallback
    ZoneInfo = None
from pathlib import Path
from typing import Any

from send_cap_policy import resolve_send_caps

ROOT = Path(__file__).resolve().parents[2]
OUTREACH_ROOT = ROOT / "outreach"
QUEUE_ROOT = OUTREACH_ROOT / "queue"
APPROVED_DIR = QUEUE_ROOT / "approved"
REVIEW_DIR = QUEUE_ROOT / "review"
SENT_DIR = QUEUE_ROOT / "sent"
POLICY_PATH = ROOT / "ops" / "agent-control" / "policies" / "outbound-policy.json"
WATCHDOG_STATE = ROOT / "ops" / "watchdog" / "state" / "latest-watchdog.json"
TCP_PRESSURE_STATE = ROOT / "ops" / "agent-control" / "state" / "latest-m4-tcp-pressure.json"
OPS_DB = ROOT / "ops" / "agent-control" / "data" / "jvt_ops.sqlite3"
INBOX_NEW = OUTREACH_ROOT / "inbox" / "new"
REPORT_DIR = OUTREACH_ROOT / "schedules" / "auto-send"
QUALITY_GATE = OUTREACH_ROOT / "tools" / "quality_gate_approved.py"
SEND_APPROVED = OUTREACH_ROOT / "tools" / "send_approved.py"
MOVE_PACKET = OUTREACH_ROOT / "tools" / "move_packet.py"

BAD_GENERIC_NAMES = {
    "tax advisory services",
    "wealth management",
    "accounting services",
    "bookkeeping services",
    "contact us",
    "home page",
}
BLOCKED_LOCAL_PARTS = {
    "career", "careers", "employment", "hr", "jobs", "recruiting", "resumes",
    "noreply", "no-reply", "donotreply", "do-not-reply", "seo", "marketing", "webmaster",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def policy_timezone(policy: dict[str, Any]):
    name = str(policy.get("timezone") or "America/New_York")
    if ZoneInfo:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return timezone.utc


def local_today(policy: dict[str, Any]) -> str:
    return datetime.now(timezone.utc).astimezone(policy_timezone(policy)).date().isoformat()


def policy_auto_send(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("auto_send")
    return value if isinstance(value, dict) else {}


def inbox_new_count() -> int:
    if not INBOX_NEW.exists():
        return 0
    return sum(1 for path in INBOX_NEW.rglob("*.json") if path.is_file())


def domain_from_url(value: str) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value if "://" in value else f"https://{value}")
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    return host.lower().removeprefix("www.")


def add_hit_item(hits: list[dict[str, str]], emails: set[str], domains: set[str], item: dict[str, str]) -> None:
    email = str(item.get("sender_email") or "").strip().lower()
    domain = str(item.get("sender_domain") or "").strip().lower()
    if not domain and "@" in email:
        domain = email.rsplit("@", 1)[1]
    if email:
        emails.add(email)
    if domain:
        domains.add(domain)
    item["sender_email"] = email
    item["sender_domain"] = domain
    hits.append(item)


def active_hit_contacts() -> dict[str, Any]:
    """Return active direct/high inbox contacts that should pause their follow-ups only."""

    hits: list[dict[str, str]] = []
    emails: set[str] = set()
    domains: set[str] = set()
    inbox_paths = sorted(INBOX_NEW.rglob("*.json")) if INBOX_NEW.exists() else []
    for path in inbox_paths:
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            continue
        bucket = str(payload.get("triage_bucket") or "").lower()
        priority = str(payload.get("triage_priority") or "").lower()
        action = str(payload.get("triage_action") or "").lower()
        if bucket != "direct" and priority != "high" and action != "review":
            continue
        email = str(payload.get("sender_email") or "").strip().lower()
        domain = str(payload.get("sender_domain") or "").strip().lower()
        if not domain and "@" in email:
            domain = email.rsplit("@", 1)[1]
        add_hit_item(hits, emails, domains, {
            "id": path.stem,
            "sender_email": email,
            "sender_domain": domain,
            "subject": str(payload.get("subject") or ""),
            "path": str(path),
        })

    if OPS_DB.exists():
        try:
            conn = sqlite3.connect(OPS_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT o.id, o.stage, o.service_slug, o.source, a.name, a.website, c.email
                FROM opportunities o
                JOIN accounts a ON a.id = o.account_id
                LEFT JOIN contacts c ON c.account_id = a.id
                WHERE o.stage IN (
                    'inbound-hit-needs-review',
                    'reply-needs-response',
                    'proposal-needed',
                    'pilot-discovery-needed',
                    'active'
                )
                ORDER BY o.updated_at DESC
                """
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            rows = []
        for row in rows:
            email = str(row["email"] or "").strip().lower()
            domain = email.rsplit("@", 1)[1] if "@" in email else domain_from_url(str(row["website"] or ""))
            add_hit_item(hits, emails, domains, {
                "id": f"opportunity-{row['id']}",
                "sender_email": email,
                "sender_domain": domain,
                "subject": f"{row['service_slug']} / {row['stage']} / {row['name']}",
                "path": str(row["source"] or OPS_DB),
            })

    return {
        "count": len(hits),
        "emails": sorted(emails),
        "domains": sorted(domains),
        "items": hits,
    }


def watchdog_critical_findings() -> list[dict[str, Any]]:
    state = load_json(WATCHDOG_STATE, {})
    findings = state.get("findings") if isinstance(state, dict) else []
    if not isinstance(findings, list):
        return []
    return [
        item for item in findings
        if isinstance(item, dict) and str(item.get("severity") or "").lower() == "critical"
    ]


def tcp_severity() -> str:
    state = load_json(TCP_PRESSURE_STATE, {})
    if not isinstance(state, dict):
        return "unknown"
    return str(state.get("severity") or "unknown").lower()


def is_internal_recipient(email: str) -> bool:
    clean = email.lower().strip()
    return clean.endswith("@jvt-technologies.com") or clean in {
        "chandruvasu@icloud.com",
        "chandruv@icloud.com",
        "chandru@jvt-technologies.com",
        "chandruv@jvt-technologies.com",
    }


def sent_breakdown_today(policy: dict[str, Any]) -> dict[str, int]:
    today = local_today(policy)
    counts = {"initial": 0, "followup": 0, "total": 0}
    if not SENT_DIR.exists():
        return counts
    for path in SENT_DIR.glob("*.json"):
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            continue
        if str(payload.get("sent_at") or "")[:10] != today:
            continue
        recipient = str(payload.get("recipient_email") or "").strip()
        if not recipient or is_internal_recipient(recipient):
            continue
        key = "followup" if payload.get("follow_up_stage") or payload.get("follow_up_parent_stem") else "initial"
        counts[key] += 1
        counts["total"] += 1
    return counts


def packet_kind(payload: dict[str, Any]) -> str:
    return "followup" if payload.get("follow_up_stage") or payload.get("follow_up_parent_stem") else "initial"


def approved_kind_counts() -> dict[str, int]:
    counts = {"initial": 0, "followup": 0, "total": 0}
    if not APPROVED_DIR.exists():
        return counts
    for path in APPROVED_DIR.glob("*.json"):
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            continue
        kind = packet_kind(payload)
        counts[kind] += 1
        counts["total"] += 1
    return counts


def conservative_hold_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    name = str(payload.get("company_name") or "").strip()
    lower_name = name.lower()
    email = str(payload.get("recipient_email") or payload.get("public_email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        reasons.append("invalid recipient email")
    elif email.split("@", 1)[0] in BLOCKED_LOCAL_PARTS:
        reasons.append("blocked recipient local part")
    if not name:
        reasons.append("missing company name")
    if lower_name in BAD_GENERIC_NAMES:
        reasons.append("generic company name")
    if ":" in name or "!" in name:
        reasons.append("marketing headline instead of company name")
    if len(name.split()) > 8:
        reasons.append("company name too long to trust without enrichment")
    return reasons


def active_hit_followup_hold_reason(payload: dict[str, Any], hits: dict[str, Any]) -> str:
    if packet_kind(payload) != "followup":
        return ""
    recipient = str(payload.get("recipient_email") or payload.get("public_email") or "").strip().lower()
    domain = recipient.rsplit("@", 1)[1] if "@" in recipient else ""
    hit_emails = set(hits.get("emails") or [])
    hit_domains = set(hits.get("domains") or [])
    if recipient and recipient in hit_emails:
        return f"active prospect hit for {recipient}; follow-up paused until handled"
    if domain and domain in hit_domains:
        return f"active prospect hit for {domain}; follow-up paused until handled"
    return ""


def move_to_review(stem: str, reason: str) -> None:
    subprocess.run(
        [sys.executable, str(MOVE_PACKET), "--stem", stem, "--from", "approved", "--to", "review"],
        cwd=str(ROOT),
        check=True,
        text=True,
        capture_output=True,
    )
    metadata_path = REVIEW_DIR / f"{stem}.json"
    payload = load_json(metadata_path, {})
    if isinstance(payload, dict):
        payload["quality_hold_reason"] = reason
        write_json(metadata_path, payload)


def run_quality_gate() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(QUALITY_GATE), "--move-held"],
        cwd=str(ROOT),
        check=False,
        text=True,
        capture_output=True,
        timeout=90,
    )
    payload: dict[str, Any] = {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    try:
        parsed = json.loads(result.stdout)
        if isinstance(parsed, dict):
            payload.update(parsed)
    except Exception:
        pass
    return payload


def select_stems(
    policy: dict[str, Any],
    max_per_run: int,
    caps: dict[str, Any] | None = None,
    sent: dict[str, int] | None = None,
    active_hits: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    sent = sent or sent_breakdown_today(policy)
    effective = (caps or {}).get("effective") if isinstance(caps, dict) else {}
    initial_cap = int((effective or {}).get("initial") or policy.get("daily_initial_send_cap") or 0)
    followup_cap = int((effective or {}).get("followup") or policy.get("daily_followup_send_cap") or 0)
    total_cap = int((effective or {}).get("total") or policy.get("max_total_outbound_per_day") or initial_cap + followup_cap)
    initial_remaining = max(0, initial_cap - sent["initial"])
    followup_remaining = max(0, followup_cap - sent["followup"])
    total_remaining = max(0, total_cap - sent["total"])
    allowed = min(max_per_run, total_remaining)
    selected: list[str] = []
    held: list[dict[str, Any]] = []

    for path in sorted(APPROVED_DIR.glob("*.json"), key=lambda item: (item.stat().st_mtime, item.name)):
        if len(selected) >= allowed:
            break
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            held.append({"stem": path.stem, "reason": "invalid metadata json"})
            continue
        reasons = conservative_hold_reasons(payload)
        if reasons:
            reason = "; ".join(reasons)
            move_to_review(path.stem, f"auto-send hold: {reason}")
            held.append({"stem": path.stem, "reason": reason})
            continue
        kind = packet_kind(payload)
        hit_reason = active_hit_followup_hold_reason(payload, active_hits or {})
        if hit_reason:
            held.append({"stem": path.stem, "reason": hit_reason})
            continue
        if kind == "followup":
            if followup_remaining <= 0:
                continue
            followup_remaining -= 1
        else:
            if initial_remaining <= 0:
                continue
            initial_remaining -= 1
        selected.append(path.stem)
    return selected, held


def run_send(stems: list[str], total_cap: int, timeout_seconds: int, send: bool) -> dict[str, Any]:
    if not stems:
        return {"returncode": 0, "stdout": "", "stderr": "", "sent_count": 0}
    cmd = [
        sys.executable,
        str(SEND_APPROVED),
        "--max-per-run",
        str(len(stems)),
        "--daily-limit",
        str(total_cap),
        "--delay-seconds",
        str(os.environ.get("JVT_SEND_DELAY_SECONDS", "2")),
    ]
    if send:
        cmd.append("--send")
    for stem in stems:
        cmd.extend(["--stem", stem])
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout_seconds)
        stdout = result.stdout.strip()
        sent_count = sum(1 for line in stdout.splitlines() if '"mode": "sent"' in line)
        return {"returncode": result.returncode, "stdout": stdout, "stderr": result.stderr.strip(), "sent_count": sent_count}
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": 124,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "").strip() if isinstance(exc.stderr, str) else "",
            "sent_count": 0,
            "timeout": True,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Quality-gated autonomous sender for JVT outreach.")
    parser.add_argument("--send", action="store_true", help="Actually send selected approved packets.")
    parser.add_argument("--max-per-run", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    args = parser.parse_args()

    policy = load_json(POLICY_PATH, {})
    if not isinstance(policy, dict):
        policy = {}
    auto_send = policy_auto_send(policy)
    max_per_run = args.max_per_run or int(auto_send.get("max_per_run") or os.environ.get("JVT_AUTO_SEND_MAX_PER_RUN") or 5)
    timeout_seconds = args.timeout_seconds or int(auto_send.get("timeout_seconds") or os.environ.get("JVT_AUTO_SEND_TIMEOUT_SECONDS") or 180)
    sent_before = sent_breakdown_today(policy)
    inbox_new = inbox_new_count()
    active_hits = active_hit_contacts()
    critical = watchdog_critical_findings()
    approved_counts = approved_kind_counts()
    caps = resolve_send_caps(
        policy,
        sent_before,
        approved_counts=approved_counts,
        inbox_new=inbox_new,
        critical_findings=critical,
        tcp_severity=tcp_severity(),
    )
    effective_caps = caps.get("effective") or {}
    total_cap = int(effective_caps.get("total") or policy.get("max_total_outbound_per_day") or policy.get("daily_initial_send_cap") or 10)

    report: dict[str, Any] = {
        "generated_at": utc_now(),
        "mode": "send" if args.send else "dry-run",
        "policy_path": str(POLICY_PATH),
        "auto_send_enabled": bool(auto_send.get("enabled")),
        "requires_operator_confirmation": bool(auto_send.get("requires_operator_confirmation", True)),
        "max_per_run": max_per_run,
        "daily_total_cap": total_cap,
        "daily_initial_cap": effective_caps.get("initial"),
        "daily_followup_cap": effective_caps.get("followup"),
        "base_caps": caps.get("base"),
        "dynamic_caps": caps,
        "approved_counts": approved_counts,
        "sent_before": sent_before,
        "guards": {},
        "active_hits": active_hits,
        "selected_stems": [],
        "held_by_runner": [],
        "quality_gate": {},
        "send_result": {},
    }

    if not auto_send.get("enabled"):
        report["status"] = "disabled"
    elif auto_send.get("requires_operator_confirmation", True):
        report["status"] = "blocked"
        report["block_reason"] = "policy still requires operator confirmation"
    else:
        allow_unrelated_sends = bool(auto_send.get("allow_unrelated_sends_with_active_hits", True))
        report["guards"] = {
            "inbox_new": inbox_new,
            "active_hit_count": active_hits.get("count", 0),
            "allow_unrelated_sends_with_active_hits": allow_unrelated_sends,
            "critical_watchdog_findings": critical,
            "tcp_severity": caps.get("health", {}).get("tcp_severity"),
        }
        if auto_send.get("requires_inbox_new_zero", True) and inbox_new and not allow_unrelated_sends:
            report["status"] = "blocked"
            report["block_reason"] = "new inbox items must be triaged first"
        elif auto_send.get("requires_no_critical_watchdog_findings", True) and critical:
            report["status"] = "blocked"
            report["block_reason"] = "critical watchdog finding active"
        else:
            quality_gate = run_quality_gate()
            report["quality_gate"] = quality_gate
            if int(quality_gate.get("returncode") or 0) != 0:
                report["status"] = "blocked"
                report["block_reason"] = "quality gate failed"
            else:
                stems, held = select_stems(policy, max_per_run, caps=caps, sent=sent_before, active_hits=active_hits)
                report["selected_stems"] = stems
                report["held_by_runner"] = held
                if not stems:
                    report["status"] = "idle"
                    report["block_reason"] = "no approved packets fit caps and quality rules"
                else:
                    send_result = run_send(stems, total_cap, timeout_seconds, args.send)
                    report["send_result"] = send_result
                    report["status"] = "sent" if args.send and send_result.get("returncode") == 0 else "dry-run" if not args.send else "send-failed"

    report["sent_after"] = sent_breakdown_today(policy)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    report_path = REPORT_DIR / f"{stamp}-auto-send.json"
    latest_path = REPORT_DIR / "latest-auto-send.json"
    write_json(report_path, report)
    write_json(latest_path, report)
    print(json.dumps({
        "status": report.get("status"),
        "selected": len(report.get("selected_stems") or []),
        "sent_today": report.get("sent_after", {}).get("total"),
        "report_path": str(report_path),
    }, indent=2))
    if report.get("status") == "send-failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
