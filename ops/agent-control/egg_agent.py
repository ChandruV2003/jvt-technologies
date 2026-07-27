#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
TASK_ROOT = CONTROL_ROOT / "tasks"
QUEUE_ROOT = REPO_ROOT / "outreach" / "queue"
INBOX_ROOT = REPO_ROOT / "outreach" / "inbox"
LEAD_RESEARCH_STATUS = REPO_ROOT / "lead-pipeline" / "state" / "auto-research-status.json"
WATCHDOG_STATE = REPO_ROOT / "ops" / "watchdog" / "state" / "latest-watchdog.json"
CODEX_ESCALATION_STATE = STATE_ROOT / "latest-codex-escalation.json"
CODEX_RESULT_STATE = STATE_ROOT / "latest-codex-escalation-result.json"
CODEX_RECOMMENDATION_MATERIALIZER_STATE = STATE_ROOT / "latest-codex-recommendation-materializer.json"
LEAD_QUALITY_AUDIT_STATE = STATE_ROOT / "latest-lead-quality-audit.json"
QUALITY_HOLD_REPAIR_STATE = STATE_ROOT / "latest-quality-hold-repair-queue.json"
FRESH_LEAD_PACKET_STATE = STATE_ROOT / "latest-fresh-lead-packet-prep.json"
CUSTOM_PILOT_PIPELINE_STATE = STATE_ROOT / "latest-custom-pilot-pipeline.json"
WARM_FOLLOWUP_SAMPLE_STATE = STATE_ROOT / "latest-warm-followup-samples.json"
VOICE_QUALITY_ROOT = REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "jvt-inbound-voice-agent" / "voice-quality"
VOICE_BRIDGE_REGRESSION_STATE = (
    REPO_ROOT
    / "products"
    / "Private-AI-Lab"
    / "apps"
    / "jvt-inbound-voice-agent"
    / "data"
    / "local-audio-bridge"
    / "latest-regression.json"
)

REPORT_JSON = STATE_ROOT / "latest-egg-agent.json"
REPORT_MD = STATE_ROOT / "latest-egg-agent.md"

TASK_DIRS = ("pending", "running", "completed", "failed", "held")
QUEUE_LABELS = ("draft", "review", "approved", "sent", "replied")
INBOX_LABELS = ("new", "reviewed", "closed")

SAFE_TASK_TYPES = {
    "refresh_growth_state",
    "work_item_materializer",
    "business_readiness_sweep",
    "model_router_status",
    "codex_escalation_status",
    "codex_escalation_request",
    "codex_recommendation_materializer",
    "jvt_ops_db_sync",
    "opportunity_hit_sync",
    "opportunity_manager_refresh",
    "custom_pilot_pipeline",
    "vertical_lead_research_refresh",
    "service_pilot_package_refresh",
    "voice_quality_sample_inventory",
    "voice_readiness_check",
    "local_audio_bridge_next_step",
    "paper_trader_health",
    "lead_quality_audit",
    "approved_quality_reconcile",
    "quality_hold_repair_queue",
    "resolve_review_quality_holds",
    "fresh_lead_packet_prep",
    "source_hygiene_report",
    "system_resource_report",
    "inbox_triage_finalize",
    "inbox_triage_brief",
    "outreach_review_queue_brief",
    "followup_review_brief",
    "warm_followup_sample_prep",
    "content_backlog_from_assets",
    "insurance_coi_proof_asset",
    "it_ballot_workflow_pilot_brief",
    "dental_voice_intake_pilot_brief",
    "meeting_to_action_content_packet",
    "offer_segment_summary",
    "venture_scout_index",
    "paper_trader_refresh",
    "priority_packet_review_queue",
    "ten_k_execution_digest",
}

MODEL_ACCEPTED_TASK_TYPES = {
    "vertical_lead_research_refresh",
    "service_pilot_package_refresh",
    "content_backlog_from_assets",
    "meeting_to_action_content_packet",
    "insurance_coi_proof_asset",
    "it_ballot_workflow_pilot_brief",
    "dental_voice_intake_pilot_brief",
    "offer_segment_summary",
    "venture_scout_index",
    "priority_packet_review_queue",
    "ten_k_execution_digest",
    "source_hygiene_report",
    "system_resource_report",
    "paper_trader_health",
    "lead_quality_audit",
    "quality_hold_repair_queue",
    "inbox_triage_finalize",
    "voice_readiness_check",
    "local_audio_bridge_next_step",
    "codex_escalation_request",
    "custom_pilot_pipeline",
    "warm_followup_sample_prep",
}

APPROVAL_GATED_PATTERNS = {
    "send email",
    "send prospect",
    "smtp",
    "stripe",
    "bank",
    "payment",
    "wire",
    "ach",
    "live trade",
    "alpaca live",
    "wallet",
    "mine",
    "mining",
    "stake",
    "staking",
    "franchise application",
    "submit application",
    "sam.gov register",
    "publish",
    "post to instagram",
    "post to youtube",
    "delete",
    "rm -rf",
}

SAFETY_BOUNDARY = (
    "Internal task generation only. No external outreach delivery, packet approval, spending, financial-account changes, "
    "market orders, crypto custody/network participation, public posting, paid provider enablement, destructive file actions, or external commitments."
)

DESIGN_ETHOS = [
    "JVT should act like an AI-led company, not a passive dashboard.",
    "Convert observations into internal work without waiting for the operator to restate obvious next steps.",
    "Favor sellable service wedges: voice intake, meeting-to-action, workflow automation, document generation, internal knowledge assistants, managed AI operations.",
    "Keep the $10k-by-2027-03-31 goal service-led until risk-adjusted evidence says otherwise.",
    "Outbound stays quality-gated: review, verify, and stage; external delivery remains capped and policy-controlled.",
    "Every autonomous action must be auditable, deduped, and safe to retry.",
]


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


def count_json(path: Path, recursive: bool = False) -> int:
    if not path.exists():
        return 0
    iterator = path.rglob("*.json") if recursive else path.glob("*.json")
    return sum(1 for item in iterator if item.is_file())


def file_age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    return max(0, int(datetime.now(timezone.utc).timestamp() - path.stat().st_mtime))


def parse_iso_age_seconds(value: Any) -> int | None:
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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()))


def as_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            return int(float(text))
        except ValueError:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return 0
            return as_count(parsed)
    return 0


def task_counts() -> dict[str, int]:
    return {name: count_json(TASK_ROOT / name) for name in TASK_DIRS}


def terminal_task_health(window_seconds: int = 86400) -> dict[str, Any]:
    """Summarize only the latest terminal outcome for each task type."""

    now = datetime.now(timezone.utc).timestamp()
    latest_by_type: dict[str, dict[str, Any]] = {}
    for outcome in ("completed", "failed", "held"):
        for path in (TASK_ROOT / outcome).glob("*.json"):
            payload = load_json(path, {})
            task_type = str(payload.get("type") or "").strip()
            if not task_type:
                continue
            updated_at = path.stat().st_mtime
            current = latest_by_type.get(task_type)
            if current and float(current["updated_at"]) >= updated_at:
                continue
            latest_by_type[task_type] = {
                "type": task_type,
                "outcome": outcome,
                "updated_at": updated_at,
                "age_seconds": max(0, int(now - updated_at)),
                "path": str(path),
            }
    recent_failed = sorted(
        task_type
        for task_type, item in latest_by_type.items()
        if item["outcome"] == "failed" and int(item["age_seconds"]) <= window_seconds
    )
    recent_held = sorted(
        task_type
        for task_type, item in latest_by_type.items()
        if item["outcome"] == "held" and int(item["age_seconds"]) <= window_seconds
    )
    return {
        "window_seconds": window_seconds,
        "latest_type_count": len(latest_by_type),
        "recent_failed_type_count": len(recent_failed),
        "recent_failed_types": recent_failed,
        "recent_held_type_count": len(recent_held),
        "recent_held_types": recent_held,
    }


def queue_counts() -> dict[str, int]:
    return {name: count_json(QUEUE_ROOT / name) for name in QUEUE_LABELS}


def inbox_counts() -> dict[str, int]:
    return {name: count_json(INBOX_ROOT / name, recursive=True) for name in INBOX_LABELS}


def task_exists(task_id: str) -> bool:
    for directory in TASK_DIRS:
        if (TASK_ROOT / directory / f"{task_id}.json").exists():
            return True
    return False


def blocked_text(text: str) -> str | None:
    normalized = text.lower()
    for phrase in sorted(APPROVAL_GATED_PATTERNS, key=len, reverse=True):
        pattern = re.escape(phrase).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", normalized):
            return phrase
    return None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "task"


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def cadence_bucket(cadence: str) -> str:
    now = datetime.now(timezone.utc)
    if cadence == "hourly":
        return now.strftime("%Y-%m-%d-h%H")
    if cadence == "six-hour":
        return f"{now.date().isoformat()}-h{(now.hour // 6) * 6:02d}"
    return now.date().isoformat()


def make_task_id(candidate: dict[str, Any]) -> str:
    task_type = str(candidate["type"])
    cadence = str(candidate.get("cadence") or "daily")
    source_key = str(candidate.get("dedupe_key") or candidate.get("goal") or task_type)
    return f"{cadence_bucket(cadence)}-egg-{slugify(task_type)}-{short_hash(source_key)}"


def count_review_followups() -> int:
    review = QUEUE_ROOT / "review"
    total = 0
    if not review.exists():
        return total
    for path in review.glob("*.json"):
        payload = load_json(path, {})
        if isinstance(payload, dict) and (payload.get("follow_up_stage") or payload.get("follow_up_parent_stem")):
            total += 1
    return total


def voice_sample_state() -> dict[str, Any]:
    sample_root = VOICE_QUALITY_ROOT / "samples"
    render_root = VOICE_QUALITY_ROOT / "renders"
    sample_count = 0
    render_count = 0
    if sample_root.exists():
        sample_count = sum(
            1
            for path in sample_root.glob("*")
            if path.is_file() and path.suffix.lower() in {".webm", ".wav", ".m4a", ".ogg", ".flac", ".mp3"}
        )
    if render_root.exists():
        render_count = sum(1 for path in render_root.glob("*") if path.is_file())
    return {"samples": sample_count, "renders": render_count}


def build_snapshot() -> dict[str, Any]:
    orchestrator = load_json(STATE_ROOT / "latest-orchestrator.json", {})
    ai_director = load_json(STATE_ROOT / "latest-ai-director.json", {})
    materializer = load_json(STATE_ROOT / "latest-work-item-materializer.json", {})
    runner = load_json(STATE_ROOT / "latest-local-task-runner.json", {})
    watchdog = load_json(WATCHDOG_STATE, {})
    model_router = load_json(STATE_ROOT / "latest-model-router.json", {})
    codex_escalation = load_json(CODEX_ESCALATION_STATE, {})
    codex_result = load_json(CODEX_RESULT_STATE, {})
    codex_recommendation_materializer = load_json(CODEX_RECOMMENDATION_MATERIALIZER_STATE, {})
    lead_quality = load_json(LEAD_QUALITY_AUDIT_STATE, {})
    quality_hold_repair = load_json(QUALITY_HOLD_REPAIR_STATE, {})
    fresh_lead_packets = load_json(FRESH_LEAD_PACKET_STATE, {})
    ops_db = load_json(STATE_ROOT / "latest-jvt-ops-db.json", {})
    opportunity = load_json(STATE_ROOT / "latest-opportunity-manager.json", {})
    custom_pilot = load_json(CUSTOM_PILOT_PIPELINE_STATE, {})
    warm_followups = load_json(WARM_FOLLOWUP_SAMPLE_STATE, {})
    voice = load_json(STATE_ROOT / "latest-voice-readiness.json", {})
    voice_bridge_regression = load_json(VOICE_BRIDGE_REGRESSION_STATE, {})
    paper = load_json(STATE_ROOT / "latest-paper-trader-health.json", {})
    source = load_json(STATE_ROOT / "latest-source-hygiene.json", {})
    system = load_json(STATE_ROOT / "latest-system-resources.json", {})
    venture = load_json(STATE_ROOT / "latest-venture-pipeline.json", {})
    lead = load_json(LEAD_RESEARCH_STATUS, {})
    queues = queue_counts()
    inbox = inbox_counts()
    tasks = task_counts()
    task_health = terminal_task_health()
    voice_bridge_age = parse_iso_age_seconds(voice_bridge_regression.get("generated_at"))
    voice_bridge_ready = bool(
        voice_bridge_regression.get("ok")
        and voice_bridge_age is not None
        and voice_bridge_age <= 86400
    )
    return {
        "generated_at": utc_now(),
        "queues": queues,
        "inbox": inbox,
        "tasks": tasks,
        "task_health": task_health,
        "followup_review_count": count_review_followups(),
        "orchestrator": {
            "generated_at": orchestrator.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(orchestrator.get("generated_at")),
            "status": orchestrator.get("status"),
            "quotas": orchestrator.get("quotas"),
            "work_item_count": len(orchestrator.get("work_items") or []) if isinstance(orchestrator.get("work_items"), list) else 0,
            "top_work_items": (orchestrator.get("work_items") or [])[:8] if isinstance(orchestrator.get("work_items"), list) else [],
        },
        "ai_director": {
            "generated_at": ai_director.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(ai_director.get("generated_at")),
            "mode": ai_director.get("mode"),
            "directive_count": len(ai_director.get("directives") or []) if isinstance(ai_director.get("directives"), list) else 0,
        },
        "materializer": {
            "generated_at": materializer.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(materializer.get("generated_at")),
            "created_count": materializer.get("created_count"),
            "skipped_count": materializer.get("skipped_count"),
            "unmatched_count": materializer.get("unmatched_count"),
        },
        "runner": {
            "generated_at": runner.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(runner.get("generated_at")),
            "ok": runner.get("ok"),
            "processed_count": runner.get("processed_count"),
            "pending_remaining": runner.get("pending_remaining"),
        },
        "watchdog": {
            "generated_at": watchdog.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(watchdog.get("generated_at")),
            "overall_ok": watchdog.get("overall_ok"),
            "finding_count": len(watchdog.get("findings") or []) if isinstance(watchdog.get("findings"), list) else 0,
        },
        "model_router": {
            "generated_at": model_router.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(model_router.get("generated_at")),
            "ok": model_router.get("ok"),
            "available_backends": model_router.get("available_backends"),
        },
        "codex_escalation": {
            "generated_at": codex_escalation.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(codex_escalation.get("generated_at")),
            "ok": codex_escalation.get("ok"),
            "enabled": codex_escalation.get("enabled"),
            "usage": codex_escalation.get("usage"),
            "policy": codex_escalation.get("policy"),
        },
        "codex_recommendation": {
            "generated_at": codex_result.get("generated_at"),
            "task_id": codex_result.get("task_id"),
            "ok": codex_result.get("ok"),
            "materializer_generated_at": codex_recommendation_materializer.get("generated_at"),
            "materializer_source_generated_at": (
                codex_recommendation_materializer.get("source") or {}
            ).get("generated_at")
            if isinstance(codex_recommendation_materializer.get("source"), dict)
            else None,
            "materializer_status": codex_recommendation_materializer.get("status"),
            "materialized": codex_recommendation_materializer.get("materialized"),
            "epic_id": codex_recommendation_materializer.get("epic_id"),
            "missing_paths": codex_recommendation_materializer.get("missing_paths"),
        },
        "lead_quality": {
            "generated_at": lead_quality.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(lead_quality.get("generated_at")),
            "sections": lead_quality.get("sections"),
        },
        "quality_hold_repair": {
            "generated_at": quality_hold_repair.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(quality_hold_repair.get("generated_at")),
            "approval_candidate_count": quality_hold_repair.get("approval_candidate_count"),
            "repair_candidate_count": quality_hold_repair.get("repair_candidate_count"),
            "hard_hold_count": quality_hold_repair.get("hard_hold_count"),
        },
        "fresh_lead_packets": {
            "generated_at": fresh_lead_packets.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(fresh_lead_packets.get("generated_at")),
            "source_research_generated_at": fresh_lead_packets.get("source_research_generated_at"),
            "staged_count": fresh_lead_packets.get("staged_count"),
            "approval_candidate_count": fresh_lead_packets.get("approval_candidate_count"),
        },
        "ops_db": {
            "generated_at": ops_db.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(ops_db.get("generated_at")),
            "ok": ops_db.get("ok"),
            "queue_counts": ops_db.get("queue_counts"),
            "inbox_counts": ops_db.get("inbox_counts"),
        },
        "opportunity_manager": {
            "generated_at": opportunity.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(opportunity.get("generated_at")),
            "qualified_count": opportunity.get("qualified_count"),
            "active_count": opportunity.get("active_count"),
            "warm_count": opportunity.get("warm_count"),
            "excluded_count": opportunity.get("excluded_count"),
            "duplicate_count": opportunity.get("duplicate_count"),
            "response_needed_count": opportunity.get("response_needed_count"),
            "top_next_actions": opportunity.get("top_next_actions"),
        },
        "custom_pilot_pipeline": {
            "generated_at": custom_pilot.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(custom_pilot.get("generated_at")),
            "qualified_count": custom_pilot.get("qualified_count"),
            "concept_count": custom_pilot.get("concept_count"),
            "excluded_count": custom_pilot.get("excluded_count"),
            "duplicate_count": custom_pilot.get("duplicate_count"),
            "warm_count": custom_pilot.get("warm_count"),
            "packet_count": custom_pilot.get("packet_count"),
            "conversion_ready_count": custom_pilot.get("conversion_ready_count"),
            "service_counts": custom_pilot.get("service_counts"),
            "next_actions": custom_pilot.get("next_actions"),
        },
        "warm_followup_samples": {
            "generated_at": warm_followups.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(warm_followups.get("generated_at")),
            "sent_company_count": warm_followups.get("sent_company_count"),
            "sample_count": warm_followups.get("sample_count"),
            "lane_counts": warm_followups.get("lane_counts"),
        },
        "voice": {
            "generated_at": voice.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(voice.get("generated_at")),
            "demo_ready": voice.get("demo_ready"),
            "live_ready": voice.get("live_ready"),
            "blockers": voice.get("blockers"),
            "local_bridge_ready": voice_bridge_ready,
            "local_bridge_age_seconds": voice_bridge_age,
            "local_bridge_regression_generated_at": voice_bridge_regression.get("generated_at"),
            "local_bridge_functional_ok": voice_bridge_regression.get("functional_ok"),
            "local_bridge_latency_ok": voice_bridge_regression.get("latency_ok"),
            "sample_state": voice_sample_state(),
        },
        "paper_trader": {
            "generated_at": paper.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(paper.get("generated_at")),
            "ok": paper.get("ok"),
            "mode": paper.get("mode"),
            "decision": paper.get("decision"),
        },
        "source_hygiene": {
            "generated_at": source.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(source.get("generated_at")),
            "status_count": source.get("status_count"),
            "important_changes": source.get("important_changes"),
        },
        "system_resources": {
            "generated_at": system.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(system.get("generated_at")),
            "ok": system.get("ok"),
            "tcp": system.get("tcp"),
        },
        "venture_pipeline": {
            "generated_at": venture.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(venture.get("generated_at")),
            "status": venture.get("status"),
            "summary": venture.get("summary"),
        },
        "lead_research": {
            "generated_at": lead.get("generated_at"),
            "age_seconds": parse_iso_age_seconds(lead.get("generated_at")),
            "new_leads_added": lead.get("new_leads_added"),
            "drafts_created": lead.get("drafts_created"),
            "drop_reasons": lead.get("drop_reasons"),
        },
        "artifact_ages": {
            "content_backlog": file_age_seconds(REPO_ROOT / "strategy" / "content-ops" / "content-idea-backlog.md"),
            "meeting_packet_today": file_age_seconds(REPO_ROOT / "strategy" / "content-ops" / f"meeting-to-action-content-packet-{datetime.now(timezone.utc).date().isoformat()}.md"),
            "insurance_proof_today": file_age_seconds(REPO_ROOT / "client-work" / "synthetic-examples" / f"insurance-coi-triage-proof-{datetime.now(timezone.utc).date().isoformat()}.md"),
            "ten_k_digest_today": file_age_seconds(REPO_ROOT / "strategy" / "venture-outputs" / f"{datetime.now(timezone.utc).date().isoformat()}-10k-execution-digest.md"),
        },
    }


def candidate(task_type: str, goal: str, *, cadence: str = "daily", priority: int = 5, feature: str = "company-autonomy", reason: str = "", dedupe_key: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": task_type,
        "goal": goal,
        "cadence": cadence,
        "priority_rank": priority,
        "feature": feature,
        "reason": reason,
        "dedupe_key": dedupe_key or f"{task_type}:{goal}",
        "payload": payload or {},
    }


def deterministic_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    queues = snapshot["queues"]
    inbox = snapshot["inbox"]
    tasks = snapshot["tasks"]
    quotas = (snapshot["orchestrator"].get("quotas") or {}) if isinstance(snapshot["orchestrator"].get("quotas"), dict) else {}
    lead = snapshot["lead_research"]
    voice = snapshot["voice"]
    custom_pilot = snapshot["custom_pilot_pipeline"]
    warm_followups = snapshot["warm_followup_samples"]
    materializer = snapshot["materializer"]
    codex_recommendation = (
        snapshot.get("codex_recommendation")
        if isinstance(snapshot.get("codex_recommendation"), dict)
        else {}
    )
    artifacts = snapshot["artifact_ages"]
    lead_quality = snapshot.get("lead_quality") if isinstance(snapshot.get("lead_quality"), dict) else {}
    quality_hold_repair = (
        snapshot.get("quality_hold_repair")
        if isinstance(snapshot.get("quality_hold_repair"), dict)
        else {}
    )
    fresh_lead_packets = (
        snapshot.get("fresh_lead_packets")
        if isinstance(snapshot.get("fresh_lead_packets"), dict)
        else {}
    )
    lead_quality_sections = lead_quality.get("sections") if isinstance(lead_quality.get("sections"), dict) else {}
    approved_quality = lead_quality_sections.get("approved") if isinstance(lead_quality_sections.get("approved"), dict) else {}
    recommendation_generated_at = codex_recommendation.get("generated_at")
    recommendation_handled = bool(
        recommendation_generated_at
        and recommendation_generated_at == codex_recommendation.get("materializer_source_generated_at")
    )
    recommendation_status = str(codex_recommendation.get("materializer_status") or "")
    recommendation_needs_materialization = bool(
        codex_recommendation.get("ok") is True and recommendation_generated_at and not recommendation_handled
    )
    recommendation_unresolved = recommendation_handled and (
        recommendation_status.startswith("tracked_")
        or recommendation_status in {"queued", "would_queue"}
    )

    if tasks.get("pending", 0) == 0 and (snapshot["orchestrator"].get("work_item_count") or 0) > 0:
        items.append(candidate("work_item_materializer", "Convert current orchestrator work items into executable internal tasks.", cadence="hourly", priority=1, feature="company-autonomy", reason="orchestrator has work items and pending queue is empty", dedupe_key="work-items"))
    if (snapshot["watchdog"].get("overall_ok") is False) or int(snapshot["watchdog"].get("finding_count") or 0) > 0:
        items.append(candidate("business_readiness_sweep", "Refresh company readiness after watchdog findings.", cadence="hourly", priority=1, feature="ops-health", reason="watchdog finding"))
    if snapshot["model_router"].get("ok") is not True:
        items.append(candidate("model_router_status", "Refresh model router readiness because model routing is not healthy.", cadence="hourly", priority=1, feature="model-runtime", reason="model router not ok"))
    if snapshot["codex_escalation"].get("ok") is not True or (snapshot["codex_escalation"].get("age_seconds") or 999999) > 3600:
        items.append(candidate("codex_escalation_status", "Refresh Codex CLI escalation readiness, caps, auth, and context-pack policy.", cadence="hourly", priority=1, feature="codex-governance", reason="codex escalation stale or unhealthy"))
    if recommendation_needs_materialization:
        items.append(candidate(
            "codex_recommendation_materializer",
            "Turn the latest actionable Codex repository recommendation into one deduplicated capped implementation epic.",
            cadence="hourly",
            priority=1,
            feature="codex-governance",
            reason="new Codex recommendation has not been materialized or marked implemented",
            dedupe_key=f"codex-recommendation:{recommendation_generated_at}",
        ))
    if snapshot["ops_db"].get("ok") is not True or (snapshot["ops_db"].get("age_seconds") or 999999) > 3600:
        items.append(candidate("jvt_ops_db_sync", "Sync durable JVT ops database state.", cadence="hourly", priority=2, feature="company-memory", reason="ops database stale or unhealthy"))
    if (snapshot["opportunity_manager"].get("warm_count") or 0) > 0 and (custom_pilot.get("age_seconds") or 999999) > 1800:
        items.append(candidate("custom_pilot_pipeline", "Refresh custom pilot packets for warm/direct opportunities.", cadence="hourly", priority=1, feature="custom-pilots", reason="warm opportunity needs custom pilot pipeline"))
    elif (custom_pilot.get("age_seconds") or 999999) > 3600:
        items.append(candidate("custom_pilot_pipeline", "Refresh custom pilot pipeline even when no active response is pending.", cadence="hourly", priority=3, feature="custom-pilots", reason="custom pilot pipeline stale"))
    if int(approved_quality.get("hold") or 0) > 0:
        items.append(candidate(
            "approved_quality_reconcile",
            "Demote approved packets that fail the canonical quality gate so clean inventory can continue safely.",
            cadence="hourly",
            priority=1,
            feature="outreach-quality",
            reason="approved packet failed canonical quality gate",
            dedupe_key="approved-quality-reconcile",
        ))
    elif (lead_quality.get("age_seconds") or 999999) > 3600:
        items.append(candidate("lead_quality_audit", "Refresh read-only lead and recipient quality audit.", cadence="hourly", priority=2, feature="outreach-quality", reason="lead quality audit stale"))
    if (materializer.get("unmatched_count") or 0) > 0:
        items.append(candidate("service_pilot_package_refresh", "Refresh pilot packages because some orchestrator work items were not mapped cleanly.", cadence="six-hour", priority=2, feature="company-autonomy", reason="unmatched materializer work items", dedupe_key="unmatched-materializer"))
    if (snapshot["orchestrator"].get("age_seconds") or 999999) > 2700:
        items.append(candidate("refresh_growth_state", "Refresh growth, orchestrator, EOM, and interop state.", cadence="hourly", priority=2, feature="core-state", reason="orchestrator stale"))
    if inbox.get("new", 0) > 0:
        items.append(candidate(
            "inbox_triage_finalize",
            "Finalize safe triage of raw inbound mailbox items into reviewed or closed internal states.",
            cadence="hourly",
            priority=1,
            feature="inbox",
            reason="new inbound items need state finalization",
            dedupe_key="inbox-triage-finalize",
        ))
        items.append(candidate("inbox_triage_brief", "Create review brief for new inbound mailbox items.", cadence="hourly", priority=2, feature="inbox", reason="new inbound items"))
    lead_generation = str(lead.get("generated_at") or "")
    handled_lead_generation = str(fresh_lead_packets.get("source_research_generated_at") or "")
    if as_count(lead.get("new_leads_added")) > 0 and lead_generation and lead_generation != handled_lead_generation:
        items.append(candidate(
            "fresh_lead_packet_prep",
            "Convert the latest qualified research leads into canonical quality-stamped review packets.",
            cadence="hourly",
            priority=1,
            feature="lead-to-outreach",
            reason="new lead-research generation has not been packetized",
            dedupe_key=f"fresh-leads:{lead_generation}",
            payload={"max_packets": min(5, max(1, as_count(lead.get("new_leads_added"))))},
        ))
    if queues.get("review", 0) > 0:
        items.append(candidate("outreach_review_queue_brief", "Create strict QA brief for current review queue packets.", cadence="six-hour", priority=2, feature="outreach-quality", reason="review queue has packets"))
    if queues.get("review", 0) > 0 and queues.get("approved", 0) == 0:
        if int(quality_hold_repair.get("approval_candidate_count") or 0) > 0 or int(
            quality_hold_repair.get("repair_candidate_count") or 0
        ) > 0:
            items.append(candidate(
                "resolve_review_quality_holds",
                "Preserve and clear only stale review quality holds that now pass the canonical classifier.",
                cadence="hourly",
                priority=1,
                feature="outreach-quality",
                reason="review backlog contains stale or repairable historical quality holds",
                dedupe_key="resolve-review-quality-holds",
            ))
        items.append(candidate(
            "quality_hold_repair_queue",
            "Diagnose review packets that pass shared quality audit but fail strict auto-approval so the approval bottleneck can be repaired safely.",
            cadence="hourly",
            priority=1,
            feature="outreach-quality",
            reason="review backlog exists while approved queue is empty",
            dedupe_key="quality-hold-repair-queue",
        ))
    if queues.get("review", 0) >= 40:
        items.append(candidate("priority_packet_review_queue", "Refresh priority packet review queue so QA focuses on the most likely revenue paths.", cadence="six-hour", priority=2, feature="outreach-quality", reason="large review backlog"))
    if snapshot.get("followup_review_count", 0) > 0 or int(quotas.get("eligible_followups") or 0) > 0:
        items.append(candidate("followup_review_brief", "Create strict no-reply follow-up review brief.", cadence="six-hour", priority=2, feature="followups", reason="follow-up work exists"))
    if queues.get("sent", 0) > 0 and (warm_followups.get("age_seconds") is None or int(warm_followups.get("age_seconds") or 999999) > 6 * 3600):
        items.append(candidate(
            "warm_followup_sample_prep",
            "Refresh review-only warm follow-up samples for every reached prospect/company.",
            cadence="six-hour",
            priority=2,
            feature="followups",
            reason="sent history exists and warm follow-up sample prep is stale",
            dedupe_key="warm-followup-samples",
        ))
    if as_count(lead.get("new_leads_added")) <= 1 or as_count(lead.get("drafts_created")) <= 1:
        items.append(candidate(
            "vertical_lead_research_refresh",
            "Run a higher-intent lead research pass for active service lanes.",
            cadence="hourly",
            priority=3,
            feature="lead-research",
            reason="lead research is weak or starved",
            payload={"lanes": ["dental_voice", "it_ballot", "local_receptionist", "insurance", "property", "construction"], "queries_per_run": 8, "results_per_query": 10, "max_new_leads": 8, "draft_limit": 4},
        ))
    usage = snapshot["codex_escalation"].get("usage") if isinstance(snapshot["codex_escalation"].get("usage"), dict) else {}
    remaining = usage.get("remaining") if isinstance(usage.get("remaining"), dict) else {}
    has_codex_budget = snapshot["codex_escalation"].get("ok") is True and int(remaining.get("total_execute") or 0) > 0
    high_value_codex_need = (
        queues.get("review", 0) >= 60
        or int((snapshot.get("task_health") or {}).get("recent_failed_type_count") or 0) >= 2
        or int(snapshot["watchdog"].get("finding_count") or 0) > 0
        or bool(snapshot["opportunity_manager"].get("response_needed_count"))
        or bool(snapshot["opportunity_manager"].get("warm_count"))
    )
    if has_codex_budget and high_value_codex_need and not recommendation_needs_materialization and not recommendation_unresolved:
        items.append(candidate(
            "codex_escalation_request",
            "Route one high-context JVT systems question to Codex CLI for a stronger read on the next bottleneck to fix.",
            cadence="hourly",
            priority=2,
            feature="codex-governance",
            reason="high-value system bottleneck with Codex budget available",
            dedupe_key="hourly-high-context-codex-system-review",
            payload={
                "execute_codex": True,
                "model": "gpt-5.5",
                "reasoning_effort": "medium",
                "sandbox": "read-only",
                "codex_prompt": (
                    "Review the current JVT Technologies system state and identify the single highest-leverage internal improvement "
                    "that would increase qualified outreach quality, pipeline autonomy, or speed toward the March 2027 $10k cash-flow goal. "
                    "Use the packed context, inspect repository/state files as needed, and return a precise implementation recommendation. "
                    "Do not perform or recommend external sends, spending, financial actions, live trading, public posting, applications, "
                    "or third-party commitments."
                ),
            },
        ))
    if voice.get("demo_ready") and not voice.get("local_bridge_ready"):
        items.append(candidate("local_audio_bridge_next_step", "Advance local audio bridge readiness while live routing stays disabled.", cadence="hourly", priority=2, feature="voice-intake", reason="voice demo ready but live bridge not ready"))
    sample_state = voice.get("sample_state") if isinstance(voice.get("sample_state"), dict) else {}
    if int(sample_state.get("samples") or 0) > 0 and int(sample_state.get("renders") or 0) == 0:
        items.append(candidate("voice_quality_sample_inventory", "Inventory voice samples and surface the next local synthesis/evaluation step.", cadence="six-hour", priority=4, feature="voice-quality", reason="voice samples exist without renders"))
    if artifacts.get("content_backlog") is None or int(artifacts.get("content_backlog") or 0) > 21600:
        items.append(candidate("content_backlog_from_assets", "Refresh content idea backlog from proof and demo assets.", cadence="six-hour", priority=4, feature="content-ops", reason="content backlog stale"))
    if artifacts.get("meeting_packet_today") is None:
        items.append(candidate("meeting_to_action_content_packet", "Create today's review-only meeting-to-action content packet.", cadence="daily", priority=4, feature="content-ops", reason="missing today's meeting packet"))
    if artifacts.get("insurance_proof_today") is None:
        items.append(candidate("insurance_coi_proof_asset", "Create today's synthetic insurance COI triage proof asset.", cadence="daily", priority=4, feature="proof-assets", reason="missing today's insurance proof"))
    items.extend([
        candidate("service_pilot_package_refresh", "Refresh active service pilot packages across voice intake, workflow automation, and proof assets.", cadence="six-hour", priority=4, feature="service-lines", reason="service-led growth cadence", dedupe_key="service-pilots"),
        candidate("custom_pilot_pipeline", "Refresh warm/direct custom-pilot conversion packets.", cadence="six-hour", priority=3, feature="custom-pilots", reason="warm/custom conversion cadence"),
        candidate("warm_followup_sample_prep", "Refresh all-reached-prospect warm follow-up samples.", cadence="six-hour", priority=3, feature="followups", reason="warm sample cadence"),
        candidate("offer_segment_summary", "Refresh offer segment review for the next manually reviewed packet batch.", cadence="daily", priority=4, feature="service-lines", reason="segment focus"),
        candidate("dental_voice_intake_pilot_brief", "Refresh dental voice intake pilot brief for the known inbound/pilot path.", cadence="daily", priority=4, feature="voice-intake", reason="dental voice lane"),
        candidate("it_ballot_workflow_pilot_brief", "Refresh BITS-style ballot workflow pilot brief with approval boundaries.", cadence="daily", priority=4, feature="workflow-automation", reason="ballot workflow lane"),
        candidate("ten_k_execution_digest", "Refresh the $10k execution digest and next-action focus.", cadence="daily", priority=5, feature="10k-goal", reason="cash-flow target cadence"),
        candidate("venture_scout_index", "Refresh venture scout index for practical revenue options.", cadence="daily", priority=5, feature="venture-research", reason="venture scout cadence"),
        candidate("paper_trader_health", "Refresh paper-only trader health and keep it research-only.", cadence="six-hour", priority=5, feature="paper-trading", reason="paper research visibility"),
        candidate("lead_quality_audit", "Refresh lead quality audit so targeting drift remains visible.", cadence="six-hour", priority=5, feature="outreach-quality", reason="quality visibility"),
        candidate("source_hygiene_report", "Refresh source hygiene so generated changes remain visible.", cadence="six-hour", priority=5, feature="repo-hygiene", reason="source visibility"),
        candidate("system_resource_report", "Refresh M4 resource and TCP readiness report.", cadence="hourly", priority=5, feature="ops-health", reason="system visibility"),
    ])
    return sorted(items, key=lambda item: int(item.get("priority_rank") or 99))


def model_generate(snapshot: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "You are JVT E.G.G. (Execution, Governance & Growth), the company operating-intelligence work generator. "
        "Return JSON only: an array of up to 3 internal tasks. Each item must have task_type, goal, feature, cadence, and reason. "
        f"Allowed task_type values: {sorted(MODEL_ACCEPTED_TASK_TYPES)}. "
        "Do not propose external outreach delivery, approvals, spending, market orders, crypto custody/network activity, public posting, paid provider enablement, destructive file actions, or external commitments. "
        f"Design ethos: {DESIGN_ETHOS}. "
        f"State JSON: {json.dumps(snapshot, sort_keys=True)[:7000]}"
    )
    payload = json.dumps({
        "task_type": "strategy",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 500,
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:8760/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=75) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": str(exc), "accepted": [], "rejected": []}
    choices = body.get("choices") if isinstance(body.get("choices"), list) else []
    message = ((choices[0] or {}).get("message") or {}) if choices else {}
    content = str(message.get("content") or "").strip()
    return {"available": True, "raw": content[:4000], "accepted": [], "rejected": [], "router": body.get("jvt_router")}


def extract_json_array(text: str) -> list[Any] | None:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    elif "[" in stripped and "]" in stripped:
        stripped = stripped[stripped.find("[") : stripped.rfind("]") + 1]
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def model_candidates(model: dict[str, Any]) -> list[dict[str, Any]]:
    if not model.get("available"):
        return []
    parsed = extract_json_array(str(model.get("raw") or ""))
    if parsed is None:
        model["rejected"].append({"reason": "model_output_not_json_array"})
        return []
    accepted: list[dict[str, Any]] = []
    for raw in parsed[:3]:
        if not isinstance(raw, dict):
            model["rejected"].append({"reason": "candidate_not_object"})
            continue
        task_type = str(raw.get("task_type") or raw.get("type") or "").strip()
        goal = re.sub(r"\s+", " ", str(raw.get("goal") or "")).strip()
        if task_type not in MODEL_ACCEPTED_TASK_TYPES:
            model["rejected"].append({"task_type": task_type, "reason": "unsupported_task_type"})
            continue
        if not goal or blocked_text(json.dumps(raw, sort_keys=True)):
            model["rejected"].append({"task_type": task_type, "reason": "blocked_or_empty_goal"})
            continue
        item = candidate(
            task_type,
            goal[:300],
            cadence=str(raw.get("cadence") or "daily") if str(raw.get("cadence") or "daily") in {"hourly", "six-hour", "daily"} else "daily",
            priority=6,
            feature=str(raw.get("feature") or "model-suggested")[:80],
            reason=f"model-suggested: {str(raw.get('reason') or '')[:180]}",
            dedupe_key=f"model:{task_type}:{goal[:160]}",
        )
        accepted.append(item)
        model["accepted"].append({"task_type": task_type, "goal": goal[:220]})
    return accepted[:2]


def build_task(candidate_item: dict[str, Any], task_id: str) -> dict[str, Any]:
    task = {
        "id": task_id,
        "type": candidate_item["type"],
        "priority": "egg",
        "created_at": utc_now(),
        "goal": candidate_item["goal"],
        "requires_approval": False,
        "seeded_by": "egg_agent",
        "feature": candidate_item.get("feature") or "company-autonomy",
        "level": "story" if candidate_item["type"] in {"vertical_lead_research_refresh", "fresh_lead_packet_prep", "service_pilot_package_refresh", "custom_pilot_pipeline", "warm_followup_sample_prep", "local_audio_bridge_next_step"} else "task",
        "model_tier": "m4-local-with-macbook-large-available" if "model-suggested" in str(candidate_item.get("reason") or "") else "deterministic",
        "self_review": "strict" if candidate_item["type"] in {"vertical_lead_research_refresh", "fresh_lead_packet_prep", "custom_pilot_pipeline", "warm_followup_sample_prep", "local_audio_bridge_next_step", "priority_packet_review_queue", "lead_quality_audit", "approved_quality_reconcile", "quality_hold_repair_queue", "inbox_triage_finalize"} else "standard",
        "source_reason": candidate_item.get("reason") or "",
        "source_agent": "egg",
        "safety_boundary": SAFETY_BOUNDARY,
    }
    task.update(candidate_item.get("payload") or {})
    return task


def create_tasks(candidates: list[dict[str, Any]], *, max_new_tasks: int, max_pending: int, dry_run: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pending = count_json(TASK_ROOT / "pending")
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    planned: set[str] = set()
    for item in candidates:
        if item.get("type") not in SAFE_TASK_TYPES:
            skipped.append({"type": item.get("type"), "reason": "unsupported_task_type"})
            continue
        blocked = blocked_text(json.dumps(item, sort_keys=True))
        if blocked:
            skipped.append({"type": item.get("type"), "reason": f"blocked_phrase:{blocked}"})
            continue
        if pending + len(created) >= max_pending:
            skipped.append({"type": item.get("type"), "reason": "pending_cap_reached"})
            continue
        if len(created) >= max_new_tasks:
            skipped.append({"type": item.get("type"), "reason": "run_cap_reached"})
            continue
        task_id = make_task_id(item)
        if task_id in planned or task_exists(task_id):
            skipped.append({"id": task_id, "type": item.get("type"), "reason": "already_exists"})
            continue
        planned.add(task_id)
        task = build_task(item, task_id)
        path = TASK_ROOT / "pending" / f"{task_id}.json"
        if not dry_run:
            write_json(path, task)
        created.append({
            "id": task_id,
            "type": item.get("type"),
            "path": str(path),
            "feature": item.get("feature"),
            "reason": item.get("reason"),
            "dry_run": dry_run,
        })
    return created, skipped


def write_markdown(report: dict[str, Any], output_path: Path = REPORT_MD) -> None:
    lines = [
        "# JVT E.G.G.",
        "",
        "- Name: `Execution, Governance & Growth`",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Mode: `{report.get('mode')}`",
        f"- Created: `{report.get('created_count')}`",
        f"- Skipped: `{report.get('skipped_count')}`",
        f"- Pending at start: `{report.get('snapshot', {}).get('tasks', {}).get('pending')}`",
        f"- Safety: {report.get('safety_boundary')}",
        "",
        "## Ethos",
        "",
    ]
    lines.extend(f"- {item}" for item in DESIGN_ETHOS)
    lines.extend(["", "## Created Tasks", ""])
    for item in report.get("created", []):
        lines.append(f"- `{item.get('id')}` -> `{item.get('type')}`: {item.get('reason')}")
    if not report.get("created"):
        lines.append("- No new tasks created; existing dedupe/caps covered the current state.")
    lines.extend(["", "## Skipped", ""])
    for item in report.get("skipped", [])[:30]:
        lines.append(f"- `{item.get('type') or item.get('id')}`: {item.get('reason')}")
    if not report.get("skipped"):
        lines.append("- None.")
    lines.extend(["", "## Model", ""])
    model = report.get("model") or {}
    lines.append(f"- Available: `{model.get('available')}`")
    if model.get("accepted"):
        lines.append(f"- Accepted model suggestions: `{len(model.get('accepted') or [])}`")
    if model.get("rejected"):
        lines.append(f"- Rejected model suggestions: `{len(model.get('rejected') or [])}`")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="JVT E.G.G.: Execution, Governance & Growth operating-intelligence task generator.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-new-tasks", type=int, default=6)
    parser.add_argument("--max-pending", type=int, default=12)
    parser.add_argument("--no-model", action="store_true")
    args = parser.parse_args()

    snapshot = build_snapshot()
    deterministic = deterministic_candidates(snapshot)
    model = {"available": False, "reason": "disabled", "accepted": [], "rejected": []}
    model_items: list[dict[str, Any]] = []
    if not args.no_model:
        model = model_generate(snapshot)
        model_items = model_candidates(model)
    candidates = deterministic + model_items
    created, skipped = create_tasks(candidates, max_new_tasks=args.max_new_tasks, max_pending=args.max_pending, dry_run=args.dry_run)
    report = {
        "generated_at": utc_now(),
        "system_name": "JVT E.G.G.",
        "system_expansion": "Execution, Governance & Growth",
        "mode": "local-model-assisted" if model.get("available") else "deterministic",
        "dry_run": args.dry_run,
        "snapshot": snapshot,
        "candidate_count": len(candidates),
        "deterministic_candidate_count": len(deterministic),
        "model_candidate_count": len(model_items),
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "skipped": skipped,
        "model": model,
        "safety_boundary": SAFETY_BOUNDARY,
    }
    report_json = STATE_ROOT / "latest-egg-agent-dry-run.json" if args.dry_run else REPORT_JSON
    report_md = STATE_ROOT / "latest-egg-agent-dry-run.md" if args.dry_run else REPORT_MD
    write_json(report_json, report)
    write_markdown(report, report_md)
    print(json.dumps({
        "ok": True,
        "mode": report["mode"],
        "created_count": report["created_count"],
        "skipped_count": report["skipped_count"],
        "json_path": str(report_json),
        "markdown_path": str(report_md),
    }, indent=2))


if __name__ == "__main__":
    main()
