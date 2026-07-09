#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - old Python fallback
    ZoneInfo = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTREACH_TOOLS = REPO_ROOT / "outreach" / "tools"
if str(OUTREACH_TOOLS) not in sys.path:
    sys.path.insert(0, str(OUTREACH_TOOLS))

from send_cap_policy import resolve_send_caps

CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
POLICY_PATH = CONTROL_ROOT / "policies" / "outbound-policy.json"
AGENT_ROOT = CONTROL_ROOT / "agents"
LEAD_DB = REPO_ROOT / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
QUEUE_ROOT = REPO_ROOT / "outreach" / "queue"
INBOX_ROOT = REPO_ROOT / "outreach" / "inbox"
FOLLOWUP_REPORT_DIR = REPO_ROOT / "outreach" / "schedules" / "followups"
COPYWRITER_REPORT = REPO_ROOT / "outreach" / "schedules" / "copywriter" / "latest-agentic-rewrite.json"
WATCHDOG_STATE = REPO_ROOT / "ops" / "watchdog" / "state" / "latest-watchdog.json"
TCP_PRESSURE_STATE = CONTROL_ROOT / "state" / "latest-m4-tcp-pressure.json"
AGENT_INTEROP_STATE = CONTROL_ROOT / "state" / "latest-agent-interop.json"
SERVICE_BOARD = REPO_ROOT / "strategy" / "service-line-execution-board.json"
REVENUE_OPPORTUNITIES = REPO_ROOT / "strategy" / "revenue-opportunities.json"
VOICE_AGENT_DATA_ROOT = REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "jvt-inbound-voice-agent" / "data"
VOICE_READINESS_STATE = STATE_ROOT / "latest-voice-readiness.json"
TRADER_ROOT = Path("/Users/c.s.d.v.r.s./Developer/JVT-AutoTrader")
CRYPTO_LAB_ROOT = Path("/Users/c.s.d.v.r.s./Developer/JVT-Crypto-Intelligence-Lab")
CRYPTO_LAB_REPORT = CRYPTO_LAB_ROOT / "reports" / "latest-feasibility.json"
VENTURE_PIPELINE_STATE = CONTROL_ROOT / "state" / "latest-venture-pipeline.json"

QUEUE_LABELS = ("draft", "review", "approved", "sent", "replied")
DECISION_LABELS = ("pending", "approved", "rejected", "executed")
INBOX_LABELS = ("new", "reviewed", "closed")
INTERNAL_RECIPIENTS = {
    "chandruvasu@icloud.com",
    "chandruv@icloud.com",
    "chandru@jvt-technologies.com",
    "chandruv@jvt-technologies.com",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def count_json(directory: Path, recursive: bool = False) -> int:
    if not directory.exists():
        return 0
    iterator = directory.rglob("*.json") if recursive else directory.glob("*.json")
    return sum(1 for item in iterator if item.is_file())


def parse_datetime(value: object, default_tz=timezone.utc) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed.astimezone(timezone.utc)


def age_seconds_from_iso(value: object) -> int | None:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    return max(0, int((utc_now() - parsed).total_seconds()))


def path_age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    return max(0, int(time.time() - path.stat().st_mtime))


def policy_timezone(policy: dict[str, Any]):
    name = str(policy.get("timezone") or "America/New_York")
    if ZoneInfo:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return timezone.utc


def local_today(policy: dict[str, Any]) -> datetime.date:
    return utc_now().astimezone(policy_timezone(policy)).date()


def is_prospect_packet(payload: dict[str, Any]) -> bool:
    recipient = str(payload.get("recipient_email") or "").strip().lower()
    company = str(payload.get("company_name") or "").strip().lower()
    return bool(recipient) and not (
        recipient in INTERNAL_RECIPIENTS
        or recipient.endswith("@jvt-technologies.com")
        or "jvt technologies" in company
        or company == "test"
        or "self-test" in company
    )


def packet_local_date(path: Path, payload: dict[str, Any], policy: dict[str, Any]) -> datetime.date | None:
    tz = policy_timezone(policy)
    parsed = parse_datetime(payload.get("sent_at") or payload.get("generated_at"), default_tz=tz)
    if parsed:
        return parsed.astimezone(tz).date()
    if path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime, tz=tz).date()
    return None


def lead_status_counts() -> dict[str, int]:
    if not LEAD_DB.exists():
        return {}
    try:
        conn = sqlite3.connect(LEAD_DB)
        rows = conn.execute("SELECT outreach_status, COUNT(*) FROM leads GROUP BY outreach_status").fetchall()
        conn.close()
    except sqlite3.Error:
        return {}
    return {str(status or "unknown"): int(count) for status, count in rows}


def queue_counts() -> dict[str, int]:
    return {label: count_json(QUEUE_ROOT / label) for label in QUEUE_LABELS}


def inbox_counts() -> dict[str, int]:
    return {label: count_json(INBOX_ROOT / label, recursive=True) for label in INBOX_LABELS}


def decision_counts() -> dict[str, int]:
    return {label: count_json(CONTROL_ROOT / label) for label in DECISION_LABELS}


def sent_breakdown(policy: dict[str, Any]) -> dict[str, int]:
    sent_dir = QUEUE_ROOT / "sent"
    today = local_today(policy)
    breakdown = {
        "initial_today": 0,
        "followup_today": 0,
        "prospect_total": 0,
        "followup_total": 0,
    }
    if not sent_dir.exists():
        return breakdown

    for path in sent_dir.glob("*.json"):
        payload = load_json(path, {})
        if not isinstance(payload, dict) or not is_prospect_packet(payload):
            continue
        is_followup = bool(payload.get("follow_up_stage") or payload.get("follow_up_parent_stem"))
        if is_followup:
            breakdown["followup_total"] += 1
        else:
            breakdown["prospect_total"] += 1
        if packet_local_date(path, payload, policy) == today:
            if is_followup:
                breakdown["followup_today"] += 1
            else:
                breakdown["initial_today"] += 1
    return breakdown


def packet_kind(payload: dict[str, Any]) -> str:
    return "followup" if payload.get("follow_up_stage") or payload.get("follow_up_parent_stem") else "initial"


def approved_kind_counts() -> dict[str, int]:
    counts = {"initial": 0, "followup": 0, "total": 0}
    approved_dir = QUEUE_ROOT / "approved"
    if not approved_dir.exists():
        return counts
    for path in approved_dir.glob("*.json"):
        payload = load_json(path, {})
        if not isinstance(payload, dict) or not is_prospect_packet(payload):
            continue
        kind = packet_kind(payload)
        counts[kind] += 1
        counts["total"] += 1
    return counts


def tcp_severity() -> str:
    payload = load_json(TCP_PRESSURE_STATE, {})
    if not isinstance(payload, dict):
        return "unknown"
    return str(payload.get("severity") or "unknown").lower()


def latest_json_in(directory: Path) -> dict[str, Any]:
    if not directory.exists():
        return {}
    paths = sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return load_json(paths[0], {}) if paths else {}


def followup_summary(policy: dict[str, Any]) -> dict[str, Any]:
    min_age_days = int(policy.get("followup_min_age_days") or 4)
    cutoff = utc_now() - timedelta(days=min_age_days)
    staged_counts = {label: 0 for label in QUEUE_LABELS}
    existing_parents: set[tuple[str, str]] = set()

    for label in QUEUE_LABELS:
        directory = QUEUE_ROOT / label
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            payload = load_json(path, {})
            if not isinstance(payload, dict):
                continue
            parent = str(payload.get("follow_up_parent_stem") or "")
            stage = str(payload.get("follow_up_stage") or "")
            if parent and stage:
                staged_counts[label] += 1
                existing_parents.add((parent, stage))

    eligible_count = 0
    sent_dir = QUEUE_ROOT / "sent"
    if sent_dir.exists():
        for path in sent_dir.glob("*.json"):
            payload = load_json(path, {})
            if not isinstance(payload, dict) or not is_prospect_packet(payload):
                continue
            if payload.get("follow_up_stage") or payload.get("follow_up_parent_stem"):
                continue
            sent_at = parse_datetime(payload.get("sent_at"))
            if sent_at and sent_at > cutoff:
                continue
            if (path.stem, "1") in existing_parents:
                continue
            eligible_count += 1

    latest_report = latest_json_in(FOLLOWUP_REPORT_DIR)
    reported_eligible = latest_report.get("eligible_count")
    if isinstance(reported_eligible, int):
        eligible_count = max(eligible_count, reported_eligible)

    return {
        "min_age_days": min_age_days,
        "eligible_count": eligible_count,
        "staged_counts": staged_counts,
        "latest_report_generated_at": latest_report.get("generated_at") or "",
        "latest_report_written_count": latest_report.get("written_count") or 0,
    }


def copywriter_summary() -> dict[str, Any]:
    report = load_json(COPYWRITER_REPORT, {})
    if not isinstance(report, dict):
        report = {}
    results = report.get("results") if isinstance(report.get("results"), list) else []
    held_count = sum(1 for item in results if isinstance(item, dict) and item.get("status") == "held")
    return {
        "report_exists": bool(report),
        "state_age_seconds": age_seconds_from_iso(report.get("generated_at")) if report else None,
        "mode": report.get("mode") or "missing",
        "result_count": report.get("result_count") or 0,
        "rewritten_count": report.get("rewritten_count") or 0,
        "held_count": held_count,
        "queues": report.get("queues") or [],
        "safety_boundary": report.get("safety_boundary") or "Rewrites staged unsent outreach packets only.",
        "latest_report_path": str(COPYWRITER_REPORT),
    }


def manifest_summary() -> dict[str, Any]:
    manifests = []
    if AGENT_ROOT.exists():
        for path in sorted(AGENT_ROOT.glob("*.json")):
            payload = load_json(path, {})
            if not isinstance(payload, dict):
                continue
            manifests.append({
                "slug": payload.get("slug") or path.stem,
                "status": payload.get("status") or "unknown",
                "mode": payload.get("mode") or "unknown",
            })
    return {
        "count": len(manifests),
        "active": sum(1 for item in manifests if item["status"] == "active"),
        "autonomous": sum(1 for item in manifests if item["mode"] == "autonomous"),
        "review_driven": sum(1 for item in manifests if item["mode"] == "review-driven"),
        "items": manifests,
    }


def service_board_summary() -> dict[str, Any]:
    board = load_json(SERVICE_BOARD, {})
    wedges = board.get("wedges") if isinstance(board, dict) else []
    if not isinstance(wedges, list):
        wedges = []
    active = [wedge for wedge in wedges if str(wedge.get("status") or "").lower() == "active"]
    next_actions = []
    for wedge in active:
        for action in wedge.get("next_actions") or []:
            next_actions.append({
                "wedge_id": wedge.get("id"),
                "wedge_name": wedge.get("name"),
                "action": action,
            })
    speculative = board.get("speculative_revenue_tracks") if isinstance(board, dict) else []
    if not isinstance(speculative, list):
        speculative = []
    return {
        "ok": bool(active),
        "updated_at": board.get("updated_at") if isinstance(board, dict) else "",
        "active_wedges": len(active),
        "wedges": active,
        "next_actions": next_actions,
        "speculative_tracks": speculative,
    }


def revenue_summary() -> dict[str, Any]:
    payload = load_json(REVENUE_OPPORTUNITIES, {})
    items = payload.get("opportunities") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []
    return {
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else "",
        "recommendation": payload.get("recommendation") if isinstance(payload, dict) else "",
        "count": len(items),
        "items": items[:5],
    }


def voice_summary() -> dict[str, Any]:
    calls = VOICE_AGENT_DATA_ROOT / "calls"
    intake = VOICE_AGENT_DATA_ROOT / "intake"
    intake_paths = list(intake.glob("*.json")) if intake.exists() else []
    latest_intake = max(intake_paths, key=lambda path: path.stat().st_mtime) if intake_paths else None
    readiness = load_json(VOICE_READINESS_STATE, {})
    return {
        "data_root_exists": VOICE_AGENT_DATA_ROOT.exists(),
        "call_count": count_json(calls),
        "intake_count": count_json(intake),
        "latest_intake_age_seconds": path_age_seconds(latest_intake) if latest_intake else None,
        "demo_ready": readiness.get("demo_ready") if isinstance(readiness, dict) else None,
        "live_ready": readiness.get("live_ready") if isinstance(readiness, dict) else None,
        "mode": readiness.get("mode") if isinstance(readiness, dict) else "",
        "response_engine": readiness.get("response_engine") if isinstance(readiness, dict) else "",
        "gates": readiness.get("gates") if isinstance(readiness, dict) else {},
        "blockers": readiness.get("blockers") if isinstance(readiness, dict) else [],
        "local_audio_bridge_health": readiness.get("local_audio_bridge_health") if isinstance(readiness, dict) else {},
    }


def trader_summary() -> dict[str, Any]:
    return {
        "root_exists": TRADER_ROOT.exists(),
        "snapshot_age_seconds": path_age_seconds(TRADER_ROOT / "state" / "latest_account_snapshot.json"),
        "backtest_age_seconds": path_age_seconds(TRADER_ROOT / "state" / "latest_backtest.json"),
        "paper_bot_age_seconds": path_age_seconds(TRADER_ROOT / "state" / "latest_paper_bot_report.json"),
        "guardrail": "Paper-only research. No live trading or fund movement.",
    }


def crypto_lab_summary() -> dict[str, Any]:
    report = load_json(CRYPTO_LAB_REPORT, {})
    return {
        "root_exists": CRYPTO_LAB_ROOT.exists(),
        "report_exists": bool(report),
        "report_age_seconds": age_seconds_from_iso(report.get("generated_at")) if isinstance(report, dict) else None,
        "verdict": report.get("verdict") if isinstance(report, dict) else "",
        "guardrail": "Read-only feasibility. No wallets, miners, staking keys, custody, or fund movement.",
    }


def venture_pipeline_summary() -> dict[str, Any]:
    report = load_json(VENTURE_PIPELINE_STATE, {})
    if not isinstance(report, dict):
        report = {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    opportunities = report.get("ranked_opportunities") if isinstance(report.get("ranked_opportunities"), list) else []
    work_items = report.get("work_items") if isinstance(report.get("work_items"), list) else []
    return {
        "report_exists": bool(report),
        "state_age_seconds": age_seconds_from_iso(report.get("generated_at")) if report else None,
        "status": report.get("status") or "missing",
        "opportunity_count": summary.get("opportunity_count") or len(opportunities),
        "top_opportunity": summary.get("top_opportunity") or (opportunities[0].get("name") if opportunities else ""),
        "top_score": summary.get("top_score") if summary else (opportunities[0].get("score") if opportunities else None),
        "work_item_count": len(work_items),
        "work_items": work_items[:8],
        "guardrail": "Internal research, scoring, and prep only. No spending, sends, applications, trades, wallets, mining, staking, or commitments.",
    }


def lane(slug: str, title: str, status: str, summary: str, metrics: dict[str, Any], next_step: str) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": title,
        "status": status,
        "summary": summary,
        "metrics": metrics,
        "next_step": next_step,
    }


def work_item(
    priority: int,
    lane_slug: str,
    title: str,
    detail: str,
    recommended_action: str,
    automation_level: str,
    blocked_by: list[str] | None = None,
) -> dict[str, Any]:
    digest = hashlib.sha1(f"{lane_slug}:{title}:{detail}".encode("utf-8")).hexdigest()[:10]
    return {
        "id": f"{priority:02d}-{lane_slug}-{digest}",
        "priority": priority,
        "lane": lane_slug,
        "title": title,
        "detail": detail,
        "recommended_action": recommended_action,
        "automation_level": automation_level,
        "blocked_by": blocked_by or [],
    }


def build_lanes(
    queues: dict[str, int],
    inbox: dict[str, int],
    leads: dict[str, int],
    followups: dict[str, Any],
    copywriter: dict[str, Any],
    board: dict[str, Any],
    voice: dict[str, Any],
    watchdog: dict[str, Any],
    interop: dict[str, Any],
    trader: dict[str, Any],
    crypto: dict[str, Any],
    venture: dict[str, Any],
    policy: dict[str, Any],
    quotas: dict[str, Any],
) -> list[dict[str, Any]]:
    total_leads = sum(leads.values())
    staged_followups = followups.get("staged_counts") or {}
    copywriter_age = copywriter.get("state_age_seconds")
    copywriter_stale = copywriter_age is None or int(copywriter_age or 0) > 2 * 3600
    copywriter_held = int(copywriter.get("held_count") or 0)
    auto_send_enabled = bool((policy.get("auto_send") or {}).get("enabled")) and not bool((policy.get("auto_send") or {}).get("requires_operator_confirmation", True))
    auto_send_has_cap = auto_send_enabled and int(quotas.get("total_remaining_today") or 0) > 0
    return [
        lane(
            "inbox-triage",
            "Inbox triage",
            "attention" if inbox.get("new", 0) else "clear",
            f"{inbox.get('new', 0)} new imported item(s), {inbox.get('reviewed', 0)} reviewed.",
            inbox,
            "Review or close new direct/review inbox items before scaling sends.",
        ),
        lane(
            "lead-research",
            "Lead research",
            "active" if LEAD_DB.exists() else "attention",
            f"{total_leads} lead record(s) tracked across outreach statuses.",
            {"total": total_leads, **leads},
            "Keep sourcing vertical-specific targets for active offers.",
        ),
        lane(
            "daily-wave",
            "Daily wave prep",
            "ready" if queues.get("review", 0) or queues.get("approved", 0) else "needs-input",
            f"{queues.get('draft', 0)} draft, {queues.get('review', 0)} review, {queues.get('approved', 0)} approved.",
            {key: queues.get(key, 0) for key in ("draft", "review", "approved", "sent")},
            "Generate or review the next wave; quality-pass sends are delegated within caps." if auto_send_enabled else "Generate or review the next wave; sending remains confirmation-gated.",
        ),
        lane(
            "qa-review",
            "QA review",
            "attention" if queues.get("review", 0) else "clear",
            f"{queues.get('review', 0)} packet(s) need recipient and copy review.",
            {"review_backlog": queues.get("review", 0)},
            "Reject placeholders and mismatched recipients before approval.",
        ),
        lane(
            "followups",
            "No-reply follow-ups",
            "attention" if followups.get("eligible_count", 0) or staged_followups.get("review", 0) else "clear",
            f"{followups.get('eligible_count', 0)} eligible older no-reply prospect(s).",
            {"eligible": followups.get("eligible_count", 0), **staged_followups},
            "Stage follow-ups separately from first-touch sends.",
        ),
        lane(
            "agentic-copywriter",
            "Agentic copywriter",
            "attention" if copywriter_stale or copywriter_held else "active",
            f"{copywriter.get('rewritten_count', 0)} model rewrite(s) from {copywriter.get('result_count', 0)} checked packet(s).",
            copywriter,
            "Review held copywriter outputs and keep model rewrites upstream of QA/auto-send." if copywriter_held else "Let the copywriter improve staged unsent packets while QA and send gates remain separate.",
        ),
        lane(
            "sender",
            "Outbound send gate",
            "auto-send-ready" if auto_send_has_cap and queues.get("approved", 0) else "auto-send-queued" if auto_send_enabled and queues.get("approved", 0) else "approval-required" if queues.get("approved", 0) else "idle",
            f"{queues.get('approved', 0)} approved packet(s) are ready for delegated quality-gated send." if auto_send_enabled else f"{queues.get('approved', 0)} approved packet(s) are ready for operator-confirmed send.",
            {"approved_backlog": queues.get("approved", 0), "auto_send_enabled": auto_send_enabled},
            "Auto-send runner processes quality-pass packets within caps." if auto_send_enabled else "Only send after human confirmation in the control panel.",
        ),
        lane(
            "offer-demos",
            "Offer demos and service lines",
            "active" if board.get("active_wedges") else "attention",
            f"{board.get('active_wedges', 0)} active service wedge(s) on the board.",
            {"active_wedges": board.get("active_wedges", 0), "next_actions": len(board.get("next_actions") or [])},
            "Turn active wedge next-actions into proof assets and targeted outreach variants.",
        ),
        lane(
            "venture-growth",
            "Venture growth pipeline",
            "active" if venture.get("report_exists") and venture.get("work_item_count", 0) else "attention",
            f"{venture.get('opportunity_count', 0)} tracked venture path(s); top path: {venture.get('top_opportunity') or 'none'}.",
            {
                "opportunities": venture.get("opportunity_count", 0),
                "work_items": venture.get("work_item_count", 0),
                "top_score": venture.get("top_score"),
            },
            "Advance the highest-scoring low-risk business-development action without crossing approval gates.",
        ),
        lane(
            "voice-intake",
            "Voice intake",
            "active" if voice.get("data_root_exists") else "attention",
            f"{voice.get('intake_count', 0)} intake packet(s), {voice.get('call_count', 0)} call record(s).",
            voice,
            "Keep dry-run intake ready; live phone use needs separate provider approval.",
        ),
        lane(
            "ops-safety",
            "Ops safety",
            "attention" if not watchdog.get("overall_ok", watchdog.get("ok")) or not interop.get("ok") else "clear",
            f"{len(watchdog.get('findings') or [])} watchdog finding(s), {interop.get('finding_count', 0)} interop finding(s).",
            {"watchdog_findings": len(watchdog.get("findings") or []), "interop_findings": interop.get("finding_count", 0)},
            "Resolve critical health checks before widening automation volume.",
        ),
        lane(
            "research-labs",
            "Paper trader and crypto lab",
            "research-only",
            "Paper trading and crypto feasibility stay read-only/paper-only.",
            {"trader_snapshot_age": trader.get("snapshot_age_seconds"), "crypto_report_age": crypto.get("report_age_seconds")},
            "Refresh reports, but do not run live trades, miners, wallets, or staking.",
        ),
    ]


def build_work_items(
    queues: dict[str, int],
    inbox: dict[str, int],
    followups: dict[str, Any],
    copywriter: dict[str, Any],
    board: dict[str, Any],
    voice: dict[str, Any],
    watchdog: dict[str, Any],
    interop: dict[str, Any],
    policy: dict[str, Any],
    trader: dict[str, Any],
    crypto: dict[str, Any],
    venture: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    watchdog_findings = watchdog.get("findings") or []
    critical_watchdog = [
        finding for finding in watchdog_findings
        if isinstance(finding, dict) and str(finding.get("severity") or "").lower() == "critical"
    ]

    if critical_watchdog:
        items.append(work_item(
            0,
            "ops-safety",
            "Fix critical watchdog findings",
            f"{len(critical_watchdog)} critical watchdog finding(s) are active.",
            "Open Watchdog Status, fix the failing health checks, then rerun watchdog and orchestrator.",
            "autonomous-detection",
        ))
    if not interop.get("ok"):
        interop_finding_count = interop.get("finding_count")
        interop_detail = (
            f"{interop_finding_count} interop finding(s) are active."
            if interop_finding_count is not None
            else "No interop state file has been generated yet."
        )
        items.append(work_item(
            1,
            "ops-safety",
            "Clean up agent interop findings",
            interop_detail,
            "Run the interop check and fix missing launch agents, endpoints, or handoffs.",
            "autonomous-detection",
        ))
    if inbox.get("new", 0):
        items.append(work_item(
            1,
            "inbox-triage",
            "Triage new inbox imports",
            f"{inbox.get('new', 0)} new inbox item(s) need review before widening outbound volume.",
            "Classify direct replies, close system/promotional items, and draft any needed human reply.",
            "stage-only",
        ))
    if queues.get("review", 0):
        items.append(work_item(
            2,
            "qa-review",
            "Review staged outreach packets",
            f"{queues.get('review', 0)} packet(s) are in review.",
            "Approve only public business inboxes or relevant owner/partner/ops contacts; reject placeholders and mismatches.",
            "requires-approval",
        ))
    if queues.get("approved", 0):
        auto_send_enabled = bool((policy.get("auto_send") or {}).get("enabled")) and not bool((policy.get("auto_send") or {}).get("requires_operator_confirmation", True))
        items.append(work_item(
            2,
            "sender",
            "Auto-send approved quality-pass packets" if auto_send_enabled else "Send approved packets after final confirmation",
            f"{queues.get('approved', 0)} packet(s) are approved. Auto-send is {auto_send_enabled}.",
            "Let the auto-send runner process quality-pass packets within caps." if auto_send_enabled else "Use the control panel send confirmation if the inbox and watchdog are clean.",
            "stage-only" if auto_send_enabled else "requires-approval",
        ))

    staged_followups = followups.get("staged_counts") or {}
    if staged_followups.get("review", 0):
        items.append(work_item(
            2,
            "followups",
            "Review staged follow-up packets",
            f"{staged_followups.get('review', 0)} follow-up packet(s) are in review.",
            "Review follow-ups independently from first-touch sends, then approve safe packets.",
            "requires-approval",
        ))
    elif followups.get("eligible_count", 0):
        items.append(work_item(
            3,
            "followups",
            "Stage no-reply follow-ups",
            f"{followups.get('eligible_count', 0)} older no-reply prospect(s) are eligible for follow-up.",
            "Generate a separate follow-up wave capped by the outbound policy.",
            "stage-only",
        ))

    if not queues.get("review", 0) and not queues.get("approved", 0):
        items.append(work_item(
            3,
            "daily-wave",
            "Prepare the next targeted outreach wave",
            "No reviewed or approved first-touch packet backlog is ready.",
            "Prepare a small wave for the highest-priority service wedge; the auto-send runner handles quality-pass sends within caps.",
            "stage-only",
        ))

    copywriter_age = copywriter.get("state_age_seconds")
    if copywriter_age is None or int(copywriter_age or 0) > 2 * 3600:
        items.append(work_item(
            2,
            "agentic-copywriter",
            "Refresh agentic copywriter pass",
            "The copywriter report is missing or older than 2 hours.",
            "Run the copywriter pass against review/approved unsent packets, then rerun interop and orchestrator.",
            "autonomous-detection",
        ))
    elif int(copywriter.get("held_count") or 0):
        items.append(work_item(
            2,
            "agentic-copywriter",
            "Review held copywriter outputs",
            f"{copywriter.get('held_count')} copywriter result(s) were held by the model/copy gate.",
            "Inspect the latest copywriter report and either tune the prompt or leave the original packet copy untouched.",
            "stage-only",
        ))

    for index, action in enumerate((board.get("next_actions") or [])[:4], start=4):
        items.append(work_item(
            index,
            "offer-demos",
            f"Advance {action.get('wedge_name') or 'service wedge'}",
            str(action.get("action") or "No action text recorded."),
            "Turn this into a proof asset, prospect list, template update, or control-panel task.",
            "stage-only",
        ))

    for index, action in enumerate((venture.get("work_items") or [])[:3], start=4):
        title = str(action.get("title") or action.get("opportunity") or "Advance venture pipeline")
        recommended = str(action.get("recommended_action") or "Prepare the next internal validation step.")
        approval_actions = action.get("approval_required_before") if isinstance(action.get("approval_required_before"), list) else []
        detail = (
            f"{action.get('opportunity') or 'Venture path'} is ranked in the growth pipeline. "
            f"Approval-gated actions: {', '.join(str(item) for item in approval_actions[:3]) or 'none recorded'}."
        )
        items.append(work_item(
            index,
            "venture-growth",
            title,
            detail,
            recommended,
            str(action.get("automation_level") or "stage-only"),
            ["operator approval"] if str(action.get("automation_level") or "") == "approval-required" else [],
        ))

    if not voice.get("data_root_exists") or not voice.get("intake_count", 0):
        items.append(work_item(
            5,
            "voice-intake",
            "Keep voice intake demo-ready",
            "Voice intake has no recent captured intake packet in this state view.",
            "Run a dry-run intake scenario and keep the public proof flow current.",
            "stage-only",
        ))
    voice_gates = voice.get("gates") if isinstance(voice.get("gates"), dict) else {}
    bridge_health = voice.get("local_audio_bridge_health") if isinstance(voice.get("local_audio_bridge_health"), dict) else {}
    if voice.get("demo_ready") and not voice.get("live_ready") and not voice_gates.get("local_audio_bridge_ready"):
        bridge_status = bridge_health.get("service_status") or bridge_health.get("status") or "unknown"
        items.append(work_item(
            4,
            "voice-intake",
            "Advance local audio bridge readiness",
            f"Voice demo mode is ready, but the local audio bridge is not production-ready. Bridge status: {bridge_status}.",
            "Run the local-audio-bridge next-step task, update bridge readiness evidence, and keep live routing disabled until the health gate is true.",
            "autonomous-detection",
        ))

    stale_trader = trader.get("paper_bot_age_seconds") is None or int(trader.get("paper_bot_age_seconds") or 0) > 24 * 3600
    if stale_trader:
        items.append(work_item(
            6,
            "research-labs",
            "Refresh paper-only trader research",
            "The paper trader report is missing or older than 24 hours.",
            "Run the paper/offline refresh only. Do not place live trades or move funds.",
            "stage-only",
        ))
    stale_crypto = crypto.get("report_age_seconds") is None or int(crypto.get("report_age_seconds") or 0) > 24 * 3600
    if stale_crypto:
        items.append(work_item(
            6,
            "research-labs",
            "Refresh crypto feasibility monitor",
            "The crypto feasibility report is missing or older than 24 hours.",
            "Refresh read-only assumptions and profitability math. Do not run miners, wallets, staking, or custody.",
            "stage-only",
        ))

    return sorted(items, key=lambda item: (int(item["priority"]), str(item["lane"]), str(item["title"])))


def build_quotas(
    policy: dict[str, Any],
    queues: dict[str, int],
    inbox: dict[str, int],
    sent: dict[str, int],
    followups: dict[str, Any],
    watchdog: dict[str, Any],
) -> dict[str, Any]:
    watchdog_findings = watchdog.get("findings") or []
    critical_watchdog = any(
        isinstance(item, dict) and str(item.get("severity") or "").lower() == "critical"
        for item in watchdog_findings
    )
    approved_counts = approved_kind_counts()
    critical_items = [item for item in watchdog_findings if isinstance(item, dict) and str(item.get("severity") or "").lower() == "critical"]
    caps = resolve_send_caps(
        policy,
        sent,
        approved_counts=approved_counts,
        inbox_new=int(inbox.get("new") or 0),
        critical_findings=critical_items,
        tcp_severity=tcp_severity(),
    )
    effective_caps = caps.get("effective") or {}
    cap_remaining = caps.get("remaining") or {}
    initial_cap = int(effective_caps.get("initial") or 0)
    followup_cap = int(effective_caps.get("followup") or 0)
    max_total = int(effective_caps.get("total") or 0)
    initial_remaining = int(cap_remaining.get("initial") or 0)
    followup_remaining = int(cap_remaining.get("followup") or 0)
    total_remaining = int(cap_remaining.get("total") or 0)
    auto_send_policy = policy.get("auto_send") if isinstance(policy.get("auto_send"), dict) else {}
    auto_send_enabled = bool(auto_send_policy.get("enabled"))
    allow_unrelated_with_hits = bool(auto_send_policy.get("allow_unrelated_sends_with_active_hits"))
    inbox_new = int(inbox.get("new") or 0)
    inbox_blocks_send = inbox_new > 0 and not (auto_send_enabled and allow_unrelated_with_hits)
    send_gate_clean = not critical_watchdog and not inbox_blocks_send
    send_allowed_now = auto_send_enabled and send_gate_clean and queues.get("approved", 0) > 0 and total_remaining > 0
    operator_send_ready = send_gate_clean and queues.get("approved", 0) > 0 and total_remaining > 0

    if critical_watchdog:
        ramp_recommendation = "Hold send expansion until inbox/watchdog blockers are clear."
    elif inbox_blocks_send:
        ramp_recommendation = "Hold sends until new inbox items are triaged."
    elif inbox_new and allow_unrelated_with_hits and queues.get("approved", 0) and total_remaining > 0:
        ramp_recommendation = "Active inbox hit is preserved; unrelated quality-pass sends can continue within caps."
    elif queues.get("approved", 0) and total_remaining <= 0:
        ramp_recommendation = "Outbound caps are full; approved packets are queued for the next cap window."
    elif queues.get("approved", 0) and auto_send_enabled:
        ramp_recommendation = "Auto-send can process approved quality-pass packets within caps."
    elif queues.get("approved", 0):
        ramp_recommendation = "Approved packets can be sent only through operator confirmation."
    elif queues.get("review", 0):
        ramp_recommendation = "Review packets before preparing a larger send day."
    else:
        ramp_recommendation = "Prepare another small, targeted wave before increasing volume."

    return {
        "daily_initial_send_cap": initial_cap,
        "daily_followup_send_cap": followup_cap,
        "max_total_outbound_per_day": max_total,
        "base_send_caps": caps.get("base"),
        "effective_send_caps": effective_caps,
        "send_cap_remaining": cap_remaining,
        "send_cap_adjustments": caps.get("adjustments") or [],
        "send_cap_health": caps.get("health") or {},
        "approved_kind_counts": approved_counts,
        "initial_sends_today": sent.get("initial_today", 0),
        "followup_sends_today": sent.get("followup_today", 0),
        "initial_remaining_today": initial_remaining,
        "followup_remaining_today": followup_remaining,
        "total_remaining_today": total_remaining,
        "approved_backlog": queues.get("approved", 0),
        "review_backlog": queues.get("review", 0),
        "eligible_followups": followups.get("eligible_count", 0),
        "inbox_new": inbox_new,
        "inbox_blocks_send": inbox_blocks_send,
        "allow_unrelated_sends_with_active_hits": allow_unrelated_with_hits,
        "auto_send_enabled": auto_send_enabled,
        "send_allowed_now": send_allowed_now,
        "operator_send_ready": operator_send_ready,
        "ramp_recommendation": ramp_recommendation,
    }


def build_report() -> dict[str, Any]:
    policy = load_json(POLICY_PATH, {})
    if not isinstance(policy, dict):
        policy = {}
    leads = lead_status_counts()
    queues = queue_counts()
    inbox = inbox_counts()
    decisions = decision_counts()
    sent = sent_breakdown(policy)
    followups = followup_summary(policy)
    copywriter = copywriter_summary()
    watchdog = load_json(WATCHDOG_STATE, {})
    interop = load_json(AGENT_INTEROP_STATE, {})
    manifests = manifest_summary()
    board = service_board_summary()
    revenue = revenue_summary()
    voice = voice_summary()
    trader = trader_summary()
    crypto = crypto_lab_summary()
    venture = venture_pipeline_summary()
    quotas = build_quotas(policy, queues, inbox, sent, followups, watchdog, )
    lanes = build_lanes(queues, inbox, leads, followups, copywriter, board, voice, watchdog, interop, trader, crypto, venture, policy, quotas)
    work_items = build_work_items(queues, inbox, followups, copywriter, board, voice, watchdog, interop, policy, trader, crypto, venture)
    blockers = [
        item for item in work_items
        if int(item.get("priority") or 99) <= 1 or item.get("blocked_by")
    ]
    ok = not blockers and bool(policy)

    return {
        "generated_at": utc_now().isoformat(timespec="seconds"),
        "ok": ok,
        "status": "ready" if ok else "attention",
        "policy": {
            "version": policy.get("version"),
            "mode": policy.get("mode") or "missing",
            "timezone": policy.get("timezone") or "America/New_York",
            "auto_send_enabled": bool((policy.get("auto_send") or {}).get("enabled")),
            "auto_approve_enabled": bool((policy.get("auto_approve") or {}).get("enabled")),
            "red_lines": policy.get("red_lines") or [],
            "path": str(POLICY_PATH),
        },
        "quotas": quotas,
        "lanes": lanes,
        "work_items": work_items[:20],
        "blockers": blockers[:10],
        "inputs": {
            "lead_counts": leads,
            "queue_counts": queues,
            "inbox_counts": inbox,
            "decision_counts": decisions,
            "sent_breakdown": sent,
            "followups": followups,
            "agentic_copywriter": copywriter,
            "manifests": manifests,
            "service_board": {
                "updated_at": board.get("updated_at"),
                "active_wedges": board.get("active_wedges"),
                "next_action_count": len(board.get("next_actions") or []),
                "speculative_track_count": len(board.get("speculative_tracks") or []),
            },
            "revenue": revenue,
            "venture_pipeline": venture,
            "voice": voice,
            "watchdog": {
                "state_age_seconds": age_seconds_from_iso(watchdog.get("generated_at")) if isinstance(watchdog, dict) else None,
                "overall_ok": watchdog.get("overall_ok") if isinstance(watchdog, dict) else False,
                "finding_count": len(watchdog.get("findings") or []) if isinstance(watchdog, dict) else 0,
            },
            "agent_interop": {
                "state_age_seconds": age_seconds_from_iso(interop.get("generated_at")) if isinstance(interop, dict) else None,
                "ok": interop.get("ok") if isinstance(interop, dict) else False,
                "finding_count": interop.get("finding_count", 0) if isinstance(interop, dict) else 0,
            },
            "trader": trader,
            "crypto_lab": crypto,
        },
        "safety_boundary": "No sends, payments, live trades, external commitments, wallets, mining, staking, or custody workflows are performed by the orchestrator.",
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    quotas = report.get("quotas") or {}
    lines = [
        "# JVT Growth OS Orchestrator",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Policy: `{(report.get('policy') or {}).get('mode')}`",
        f"- Safety: {report.get('safety_boundary')}",
        "",
        "## Quotas",
        "",
        f"- Initial sends today: `{quotas.get('initial_sends_today')}/{quotas.get('daily_initial_send_cap')}`",
        f"- Follow-up sends today: `{quotas.get('followup_sends_today')}/{quotas.get('daily_followup_send_cap')}`",
        f"- Total sends today: `{(quotas.get('initial_sends_today') or 0) + (quotas.get('followup_sends_today') or 0)}/{quotas.get('max_total_outbound_per_day')}`",
        f"- Dynamic cap adjustments: `{'; '.join(quotas.get('send_cap_adjustments') or []) or 'none'}`",
        f"- Approved backlog: `{quotas.get('approved_backlog')}`",
        f"- Send gate: `{'auto-send-ready' if quotas.get('auto_send_enabled') and quotas.get('operator_send_ready') else 'operator-ready' if quotas.get('operator_send_ready') else 'not-ready'}`",
        f"- Recommendation: {quotas.get('ramp_recommendation')}",
        "",
        "## Lanes",
        "",
    ]
    for item in report.get("lanes", []):
        lines.append(f"- `{item.get('status')}` {item.get('title')}: {item.get('summary')}")
    lines.extend(["", "## Work Items", ""])
    for item in report.get("work_items", [])[:12]:
        lines.append(f"- P{item.get('priority')} `{item.get('lane')}` {item.get('title')} - {item.get('recommended_action')}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the JVT Growth OS orchestrator state.")
    parser.add_argument("--state-dir", type=Path, default=STATE_ROOT)
    args = parser.parse_args()

    report = build_report()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.state_dir / "latest-orchestrator.json"
    markdown_path = args.state_dir / "latest-orchestrator.md"
    write_json(json_path, report)
    write_markdown(report, markdown_path)
    print(json.dumps({
        "ok": report["ok"],
        "status": report["status"],
        "work_items": len(report.get("work_items") or []),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }))


if __name__ == "__main__":
    main()
