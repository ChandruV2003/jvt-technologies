#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jvt_ops_db
import opportunity_manager


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
OPS_DB = CONTROL_ROOT / "data" / "jvt_ops.sqlite3"
REPORT_JSON = STATE_ROOT / "latest-conversion-pipeline.json"
REPORT_MD = STATE_ROOT / "latest-conversion-pipeline.md"
GOAL_AMOUNT = 10_000.0

SERVICE_VALUE_BANDS = {
    "ai-voice-intake": (750.0, 1_500.0),
    "workflow-automation": (2_500.0, 7_500.0),
    "private-doc-intel": (1_500.0, 5_000.0),
    "document-generation": (750.0, 2_500.0),
    "inbox-document-triage": (750.0, 2_500.0),
    "meeting-to-action": (500.0, 1_500.0),
    "managed-ai-ops": (500.0, 2_000.0),
    "knowledge-assistant": (1_500.0, 5_000.0),
}

STAGE_DEFAULTS = {
    "inbound-hit-needs-review": ("qualified", 0.10),
    "reply-needs-response": ("qualified", 0.15),
    "reply-sent-awaiting-next": ("warm", 0.20),
    "pilot-discovery-needed": ("discovery", 0.30),
    "proposal-needed": ("proposal", 0.40),
    "active": ("pilot", 0.65),
    "won": ("won", 1.00),
    "lost": ("lost", 0.00),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-").replace("--", "-")


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


def source_event_at(item: dict[str, Any]) -> datetime:
    source = Path(str(item.get("source") or ""))
    payload = load_json(source, {})
    for key in ("response_sent_at", "captured_at", "date"):
        value = str(payload.get(key) or "").strip()
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    value = str(item.get("updated_at") or item.get("created_at") or "")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def asset_state(account_name: str) -> dict[str, str]:
    slug = slugify(account_name)
    candidates = {
        "proposal": REPO_ROOT / "client-work" / "proposals" / f"{slug}-pilot-proposal.md",
        "sow": REPO_ROOT / "client-work" / "statements-of-work" / f"{slug}-draft-sow.md",
        "pilot_packet": REPO_ROOT / "client-work" / "prospect-pilot-packets",
        "proof": REPO_ROOT / "client-work" / "synthetic-examples",
    }
    paths: dict[str, str] = {}
    for key in ("proposal", "sow"):
        path = candidates[key]
        if path.exists():
            paths[key] = str(path)
    packet_matches = sorted(candidates["pilot_packet"].glob(f"*{slug}*custom-pilot.md"))
    proof_matches = sorted(candidates["proof"].glob(f"*{slug}*.md"))
    if packet_matches:
        paths["pilot_packet"] = str(packet_matches[-1])
    if proof_matches:
        paths["proof"] = str(proof_matches[-1])
    if "sow" in paths:
        stage = "sow-ready"
    elif "proposal" in paths:
        stage = "proposal-ready"
    elif "pilot_packet" in paths or "proof" in paths:
        stage = "proof-ready"
    else:
        stage = "none"
    return {"stage": stage, **paths}


def next_action_for(item: dict[str, Any], pipeline_stage: str, assets: dict[str, str]) -> tuple[str, str]:
    event_at = source_event_at(item)
    if pipeline_stage == "warm":
        due = event_at + timedelta(days=7)
        action = (
            "Review the prepared custom pilot follow-up and decide whether to send a specific next-step question; "
            "keep this contact out of generic no-reply automation."
        )
    elif pipeline_stage == "qualified":
        due = event_at + timedelta(days=2)
        action = "Prepare a specific discovery response and one matching synthetic proof asset."
    elif pipeline_stage == "discovery":
        due = event_at + timedelta(days=3)
        action = "Collect workflow, approval, sensitive-data, and success-metric details for a narrow paid pilot."
    elif pipeline_stage == "proposal":
        due = event_at + timedelta(days=3)
        action = "Review the proposal scope, pricing hypothesis, and next meeting ask."
    elif pipeline_stage == "pilot":
        due = event_at + timedelta(days=7)
        action = "Update the delivery milestone, acceptance evidence, invoice readiness, and next client checkpoint."
    elif pipeline_stage in {"won", "lost"}:
        due = event_at + timedelta(days=30)
        action = "Keep the outcome, cash, and lessons-learned record current."
    else:
        due = event_at + timedelta(days=7)
        action = "Review and assign a commercial stage."
    if assets.get("stage") == "none" and pipeline_stage not in {"won", "lost"}:
        action = f"Prepare the first prospect-specific proof asset. {action}"
    return action, due.isoformat(timespec="seconds")


def ensure_schema(conn: sqlite3.Connection) -> None:
    jvt_ops_db.create_schema(conn)


def upsert_commercial(conn: sqlite3.Connection, item: dict[str, Any]) -> dict[str, Any]:
    opportunity_id = int(item["id"])
    service_slug = str(item.get("service_slug") or "managed-ai-ops")
    pipeline_stage, probability = STAGE_DEFAULTS.get(str(item.get("stage") or ""), ("qualified", 0.10))
    low, high = SERVICE_VALUE_BANDS.get(service_slug, (500.0, 2_000.0))
    assets = asset_state(str(item.get("account_name") or ""))
    next_action, due_at = next_action_for(item, pipeline_stage, assets)
    existing = conn.execute(
        "SELECT * FROM opportunity_commercial WHERE opportunity_id=?",
        (opportunity_id,),
    ).fetchone()
    now = utc_now()
    stage_source = str(existing["stage_source"]) if existing else "egg-auto"
    if existing and stage_source == "manual":
        pipeline_stage = str(existing["pipeline_stage"])
        probability = float(existing["probability"])
        low = float(existing["estimated_value_low"])
        high = float(existing["estimated_value_high"])
        next_action = str(existing["next_action"] or next_action)
        due_at = str(existing["next_action_due_at"] or due_at)
    cash_collected = float(existing["cash_collected"]) if existing else 0.0
    weighted_value = round(((low + high) / 2.0) * probability, 2)
    metadata = {
        "account_name": item.get("account_name"),
        "service_slug": service_slug,
        "source_stage": item.get("stage"),
        "source": item.get("source"),
        "assets": assets,
    }
    conn.execute(
        """
        INSERT INTO opportunity_commercial(
          opportunity_id, pipeline_stage, asset_stage, estimated_value_low, estimated_value_high,
          probability, weighted_value, cash_collected, next_action, next_action_due_at,
          stage_source, metadata_json, created_at, updated_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(opportunity_id) DO UPDATE SET
          pipeline_stage=excluded.pipeline_stage,
          asset_stage=excluded.asset_stage,
          estimated_value_low=excluded.estimated_value_low,
          estimated_value_high=excluded.estimated_value_high,
          probability=excluded.probability,
          weighted_value=excluded.weighted_value,
          cash_collected=excluded.cash_collected,
          next_action=excluded.next_action,
          next_action_due_at=excluded.next_action_due_at,
          stage_source=excluded.stage_source,
          metadata_json=excluded.metadata_json,
          updated_at=excluded.updated_at
        """,
        (
            opportunity_id,
            pipeline_stage,
            assets["stage"],
            low,
            high,
            probability,
            weighted_value,
            cash_collected,
            next_action,
            due_at,
            stage_source,
            json.dumps(metadata),
            str(existing["created_at"]) if existing else now,
            now,
        ),
    )
    due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return {
        "opportunity_id": opportunity_id,
        "account_name": item.get("account_name"),
        "contact_email": item.get("contact_email"),
        "service_slug": service_slug,
        "service_name": item.get("service_name") or service_slug,
        "source_stage": item.get("stage"),
        "pipeline_stage": pipeline_stage,
        "asset_stage": assets["stage"],
        "assets": {key: value for key, value in assets.items() if key != "stage"},
        "estimated_value_low": low,
        "estimated_value_high": high,
        "probability": probability,
        "weighted_value": weighted_value,
        "cash_collected": cash_collected,
        "next_action": next_action,
        "next_action_due_at": due_at,
        "next_action_overdue": due < datetime.now(timezone.utc) and pipeline_stage not in {"won", "lost"},
        "stage_source": stage_source,
    }


def build_report() -> dict[str, Any]:
    conn = sqlite3.connect(OPS_DB)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    items = [item for item in opportunity_manager.fetch_items() if item.get("qualified") and not item.get("duplicate")]
    pipeline = [upsert_commercial(conn, item) for item in items]
    conn.commit()
    conn.close()
    stage_counts: dict[str, int] = {}
    for item in pipeline:
        stage = str(item["pipeline_stage"])
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    cash = round(sum(float(item["cash_collected"]) for item in pipeline), 2)
    weighted = round(sum(float(item["weighted_value"]) for item in pipeline if item["pipeline_stage"] not in {"won", "lost"}), 2)
    midpoint = round(
        sum((float(item["estimated_value_low"]) + float(item["estimated_value_high"])) / 2.0 for item in pipeline if item["pipeline_stage"] not in {"won", "lost"}),
        2,
    )
    overdue = [item for item in pipeline if item["next_action_overdue"]]
    report = {
        "generated_at": utc_now(),
        "ok": True,
        "goal": {
            "target": GOAL_AMOUNT,
            "cash_collected": cash,
            "remaining": max(0.0, round(GOAL_AMOUNT - cash, 2)),
            "weighted_pipeline": weighted,
            "open_pipeline_midpoint": midpoint,
            "coverage_ratio": round(weighted / GOAL_AMOUNT, 3) if GOAL_AMOUNT else 0,
        },
        "opportunity_count": len(pipeline),
        "stage_counts": stage_counts,
        "stale_next_action_count": len(overdue),
        "items": sorted(pipeline, key=lambda item: (not item["next_action_overdue"], -float(item["weighted_value"]))),
        "guardrail": (
            "Internal commercial memory and planning only. No invoice, payment request, contract, pricing commitment, "
            "prospect message, or external action is performed."
        ),
    }
    write_json(REPORT_JSON, report)
    write_markdown(report)
    return report


def write_markdown(report: dict[str, Any]) -> None:
    goal = report["goal"]
    lines = [
        "# JVT Conversion Pipeline",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Qualified opportunities: `{report['opportunity_count']}`",
        f"- Cash collected: `${goal['cash_collected']:,.2f}`",
        f"- Weighted pipeline: `${goal['weighted_pipeline']:,.2f}`",
        f"- Open pipeline midpoint: `${goal['open_pipeline_midpoint']:,.2f}`",
        f"- Goal remaining: `${goal['remaining']:,.2f}`",
        f"- Overdue next actions: `{report['stale_next_action_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "## Pipeline",
        "",
    ]
    if not report["items"]:
        lines.append("- No qualified commercial opportunities.")
    for item in report["items"]:
        lines.extend(
            [
                f"### {item['account_name']}",
                "",
                f"- Stage: `{item['pipeline_stage']}` from `{item['source_stage']}`",
                f"- Service: `{item['service_slug']}`",
                f"- Asset readiness: `{item['asset_stage']}`",
                f"- Value hypothesis: `${item['estimated_value_low']:,.0f}-${item['estimated_value_high']:,.0f}`",
                f"- Probability / weighted value: `{item['probability']:.0%}` / `${item['weighted_value']:,.2f}`",
                f"- Cash collected: `${item['cash_collected']:,.2f}`",
                f"- Next action due: `{item['next_action_due_at']}`",
                f"- Next action: {item['next_action']}",
                "",
            ]
        )
    REPORT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2))
