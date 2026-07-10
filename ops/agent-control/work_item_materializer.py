#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
TASK_ROOT = CONTROL_ROOT / "tasks"
EPIC_ROOT = CONTROL_ROOT / "epics"
POLICY_PATH = CONTROL_ROOT / "policies" / "work-item-materializer-policy.json"
ORCHESTRATOR_PATH = STATE_ROOT / "latest-orchestrator.json"
REPORT_JSON_PATH = STATE_ROOT / "latest-work-item-materializer.json"
REPORT_MD_PATH = STATE_ROOT / "latest-work-item-materializer.md"

TASK_DIRS = ("pending", "running", "completed", "failed", "held")
EPIC_DIRS = ("queued", "running", "done", "blocked", "held")

DEFAULT_POLICY = {
    "version": 1,
    "enabled": True,
    "materializer": {
        "default_cadence": "daily",
        "dedupe_scope": "cadence_bucket_and_work_item_id",
        "max_items_per_run": 20,
    },
    "rules": [
        {
            "name": "voice bridge readiness next step",
            "lane": "voice-intake",
            "title_contains": ["local audio bridge"],
            "action": "task",
            "task_type": "local_audio_bridge_next_step",
            "cadence": "hourly",
            "level": "story",
            "feature": "voice-intake",
            "model_tier": "deterministic-plus-m4-local-review",
            "self_review": "strict",
        },
        {
            "name": "follow-up review queue brief",
            "lane": "followups",
            "title_contains": ["follow-up"],
            "action": "task",
            "task_type": "followup_review_brief",
            "cadence": "daily",
            "level": "task",
            "feature": "followups",
            "model_tier": "deterministic",
            "self_review": "strict",
        },
        {
            "name": "outreach review queue brief",
            "lane": "qa-review",
            "title_contains": ["outreach"],
            "action": "task",
            "task_type": "outreach_review_queue_brief",
            "cadence": "daily",
            "level": "task",
            "feature": "outreach-quality",
            "model_tier": "deterministic",
            "self_review": "strict",
        },
        {
            "name": "voice intake proof asset refresh",
            "lane": "offer-demos",
            "title_contains": ["ai receptionist", "voice intake"],
            "action": "task",
            "task_type": "service_pilot_package_refresh",
            "cadence": "daily",
            "dedupe": "rule",
            "level": "feature",
            "feature": "service-lines",
            "model_tier": "m4-local-with-macbook-large-available",
            "self_review": "standard",
        },
        {
            "name": "productized services summary",
            "lane": "venture-growth",
            "title_contains": ["productized services"],
            "action": "task",
            "task_type": "offer_segment_summary",
            "cadence": "daily",
            "level": "story",
            "feature": "service-lines",
            "model_tier": "m4-local-with-macbook-large-available",
            "self_review": "standard",
        },
        {
            "name": "dental voice pilot brief",
            "lane": "venture-growth",
            "title_contains": ["dental", "voice"],
            "action": "task",
            "task_type": "dental_voice_intake_pilot_brief",
            "cadence": "daily",
            "level": "story",
            "feature": "voice-intake",
            "model_tier": "m4-local-with-macbook-large-available",
            "self_review": "standard",
        },
        {
            "name": "bits ballot workflow pilot brief",
            "lane": "venture-growth",
            "title_contains": ["ballot"],
            "action": "task",
            "task_type": "it_ballot_workflow_pilot_brief",
            "cadence": "daily",
            "level": "story",
            "feature": "workflow-automation",
            "model_tier": "m4-local-with-macbook-large-available",
            "self_review": "standard",
        },
        {
            "name": "crypto feasibility read-only refresh",
            "lane": "research-labs",
            "title_contains": ["crypto feasibility"],
            "action": "task",
            "task_type": "venture_scout_index",
            "cadence": "daily",
            "level": "task",
            "feature": "venture-research",
            "model_tier": "deterministic",
            "self_review": "standard",
        },
    ],
    "epic_rules": [
        {
            "name": "unmapped stage-only work item review",
            "automation_level": "stage-only",
            "action": "epic_spec",
            "cadence": "daily",
            "min_priority": 5,
            "level": "epic",
            "feature": "company-autonomy",
            "model_tier": "codex-cli-capped",
            "enabled": False,
            "reason": "Disabled by default to prevent broad Codex CLI usage. Enable only after ROI and acceptance criteria are explicit.",
        }
    ],
}

SAFETY_BOUNDARY = (
    "Internal task/spec creation only. No external outreach delivery, packet approval, spending, financial-account changes, "
    "market orders, crypto custody/network participation, public posting, paid provider enablement, or external commitments."
)

TEXT_REPLACEMENTS = {
    "send email": "external outreach delivery",
    "send prospect": "external prospect outreach",
    "smtp": "mail transport",
    "stripe": "billing processor",
    "bank": "financial institution",
    "payment": "billing",
    "wire": "fund transfer",
    "ach": "fund transfer",
    "live trade": "market order",
    "alpaca live": "brokerage production mode",
    "wallets": "crypto custody tools",
    "wallet": "crypto custody tool",
    "miners": "crypto extraction tools",
    "mining": "crypto extraction",
    "mine": "crypto extraction",
    "staking": "validator-yield activity",
    "stake": "validator-yield action",
    "franchise application": "franchise intake form",
    "submit application": "file external form",
    "sam.gov register": "public-vendor registration",
    "publish": "make public",
    "post to instagram": "platform posting",
    "post to youtube": "platform posting",
    "delete": "remove",
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


def merge_policy(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return DEFAULT_POLICY
    merged = json.loads(json.dumps(DEFAULT_POLICY))
    for key, value in raw.items():
        if key in {"rules", "epic_rules"} and isinstance(value, list):
            merged[key] = value
        elif key == "materializer" and isinstance(value, dict):
            merged["materializer"].update(value)
        else:
            merged[key] = value
    return merged


def ensure_dirs() -> None:
    for directory in TASK_DIRS:
        (TASK_ROOT / directory).mkdir(parents=True, exist_ok=True)
    for directory in EPIC_DIRS:
        (EPIC_ROOT / directory).mkdir(parents=True, exist_ok=True)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)


def cadence_bucket(cadence: str) -> str:
    now = datetime.now(timezone.utc)
    if cadence == "hourly":
        return now.strftime("%Y-%m-%d-h%H")
    if cadence == "six-hour":
        bucket = (now.hour // 6) * 6
        return f"{now.date().isoformat()}-h{bucket:02d}"
    return now.date().isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "work-item"


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def item_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("id", "lane", "title", "detail", "recommended_action", "automation_level")
    ).lower()


def safe_text(value: Any) -> str:
    text = str(value or "")
    for source, replacement in sorted(TEXT_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.escape(source).replace(r"\ ", r"\s+")
        text = re.sub(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", replacement, text, flags=re.IGNORECASE)
    return text


def safe_work_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: safe_text(value) if isinstance(value, str) else value
        for key, value in item.items()
    }


def title_matches(item: dict[str, Any], phrases: list[Any]) -> bool:
    text = item_text(item)
    return all(str(phrase).lower() in text for phrase in phrases)


def rule_matches(item: dict[str, Any], rule: dict[str, Any]) -> bool:
    if not rule.get("enabled", True):
        return False
    if rule.get("lane") and str(item.get("lane") or "") != str(rule.get("lane")):
        return False
    if rule.get("automation_level") and str(item.get("automation_level") or "") != str(rule.get("automation_level")):
        return False
    if rule.get("min_priority") is not None:
        try:
            if int(item.get("priority") or 999) < int(rule["min_priority"]):
                return False
        except (TypeError, ValueError):
            return False
    phrases = rule.get("title_contains")
    if isinstance(phrases, list) and phrases:
        return title_matches(item, phrases)
    return True


def existing_artifact(root: Path, directories: tuple[str, ...], artifact_id: str) -> Path | None:
    for directory in directories:
        path = root / directory / f"{artifact_id}.json"
        if path.exists():
            return path
    return None


def make_materialized_id(prefix: str, bucket: str, rule: dict[str, Any], item: dict[str, Any]) -> str:
    action = str(rule.get("task_type") or rule.get("name") or "work-item")
    dedupe = str(rule.get("dedupe") or "work_item")
    if dedupe == "rule":
        source_key = str(rule.get("name") or action)
    elif dedupe == "task_type":
        source_key = action
    else:
        source_key = str(item.get("id") or item_text(item))
    return f"{bucket}-{prefix}-{slugify(action)}-{short_hash(source_key)}"


def build_task(rule: dict[str, Any], item: dict[str, Any], task_id: str) -> dict[str, Any]:
    safe_item = safe_work_item(item)
    return {
        "id": task_id,
        "type": rule["task_type"],
        "priority": "materialized-work-item",
        "created_at": utc_now(),
        "goal": (
            f"Materialized from orchestrator work item '{safe_text(item.get('title'))}'. "
            f"Recommended action: {safe_text(item.get('recommended_action') or 'No action text provided.')}"
        ),
        "requires_approval": False,
        "seeded_by": "work_item_materializer",
        "source_orchestrator_generated_at": load_json(ORCHESTRATOR_PATH, {}).get("generated_at"),
        "source_work_item": safe_item,
        "source_work_item_raw_ref": {
            "id": item.get("id"),
            "orchestrator_state": str(ORCHESTRATOR_PATH),
        },
        "source_rule": rule.get("name"),
        "lane": item.get("lane"),
        "level": rule.get("level") or "task",
        "feature": rule.get("feature") or item.get("lane") or "general-ops",
        "model_tier": rule.get("model_tier") or "deterministic",
        "self_review": rule.get("self_review") or "standard",
        "safety_boundary": SAFETY_BOUNDARY,
    }


def build_epic_spec(rule: dict[str, Any], item: dict[str, Any], epic_id: str) -> dict[str, Any]:
    return {
        "id": epic_id,
        "title": f"Materialized review: {item.get('title')}",
        "created_at": utc_now(),
        "queued_by": "work_item_materializer",
        "level": "epic",
        "feature": rule.get("feature") or item.get("lane") or "company-autonomy",
        "model_tier": "codex-cli-capped",
        "source_work_item": item,
        "source_rule": rule.get("name"),
        "roi_case": (
            "Only run if this work removes a recurring manual blocker or opens a concrete revenue/proof-asset lane. "
            "Otherwise keep it as local task planning."
        ),
        "acceptance_criteria": [
            "Define the smallest safe internal deliverable.",
            "Identify approval-gated actions and keep them blocked.",
            "Produce a validation artifact under ops/agent-control/state or strategy/client-work.",
            "Do not perform external outreach delivery, spending, market orders, public release, crypto network participation, or external form filing.",
        ],
        "safety_boundary": SAFETY_BOUNDARY,
        "status": "queued",
    }


def materialize(*, dry_run: bool) -> dict[str, Any]:
    ensure_dirs()
    policy = merge_policy(load_json(POLICY_PATH, DEFAULT_POLICY))
    orchestrator = load_json(ORCHESTRATOR_PATH, {})
    work_items = orchestrator.get("work_items") if isinstance(orchestrator.get("work_items"), list) else []
    max_items = int(((policy.get("materializer") or {}).get("max_items_per_run")) or 20)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    planned_task_ids: set[str] = set()
    planned_epic_ids: set[str] = set()

    if not policy.get("enabled", True):
        report = {
            "generated_at": utc_now(),
            "ok": True,
            "enabled": False,
            "dry_run": dry_run,
            "created": created,
            "skipped": skipped,
            "unmatched": unmatched,
            "safety_boundary": SAFETY_BOUNDARY,
        }
        return report

    rules = policy.get("rules") if isinstance(policy.get("rules"), list) else []
    epic_rules = policy.get("epic_rules") if isinstance(policy.get("epic_rules"), list) else []

    for item in [candidate for candidate in work_items if isinstance(candidate, dict)][:max_items]:
        matched = False
        for rule in rules:
            if not isinstance(rule, dict) or not rule_matches(item, rule):
                continue
            matched = True
            cadence = str(rule.get("cadence") or ((policy.get("materializer") or {}).get("default_cadence")) or "daily")
            artifact_id = make_materialized_id("materialized", cadence_bucket(cadence), rule, item)
            if artifact_id in planned_task_ids:
                skipped.append({
                    "kind": "task",
                    "id": artifact_id,
                    "reason": "already_planned_this_run",
                    "source_work_item_id": item.get("id"),
                    "rule": rule.get("name"),
                })
                continue
            existing = existing_artifact(TASK_ROOT, TASK_DIRS, artifact_id)
            if existing:
                skipped.append({
                    "kind": "task",
                    "id": artifact_id,
                    "reason": "already_exists",
                    "path": str(existing),
                    "source_work_item_id": item.get("id"),
                    "rule": rule.get("name"),
                })
                continue
            task = build_task(rule, item, artifact_id)
            path = TASK_ROOT / "pending" / f"{artifact_id}.json"
            if not dry_run:
                write_json(path, task)
            planned_task_ids.add(artifact_id)
            created.append({
                "kind": "task",
                "id": artifact_id,
                "type": task.get("type"),
                "path": str(path),
                "source_work_item_id": item.get("id"),
                "rule": rule.get("name"),
                "dry_run": dry_run,
            })
        if matched:
            continue
        for rule in epic_rules:
            if not isinstance(rule, dict) or not rule_matches(item, rule):
                continue
            matched = True
            if not rule.get("enabled", False):
                skipped.append({
                    "kind": "epic",
                    "reason": "epic_rule_disabled",
                    "source_work_item_id": item.get("id"),
                    "rule": rule.get("name"),
                    "note": rule.get("reason"),
                })
                continue
            cadence = str(rule.get("cadence") or "daily")
            artifact_id = make_materialized_id("epic", cadence_bucket(cadence), rule, item)
            if artifact_id in planned_epic_ids:
                skipped.append({
                    "kind": "epic",
                    "id": artifact_id,
                    "reason": "already_planned_this_run",
                    "source_work_item_id": item.get("id"),
                    "rule": rule.get("name"),
                })
                continue
            existing = existing_artifact(EPIC_ROOT, EPIC_DIRS, artifact_id)
            if existing:
                skipped.append({
                    "kind": "epic",
                    "id": artifact_id,
                    "reason": "already_exists",
                    "path": str(existing),
                    "source_work_item_id": item.get("id"),
                    "rule": rule.get("name"),
                })
                continue
            epic = build_epic_spec(rule, item, artifact_id)
            path = EPIC_ROOT / "queued" / f"{artifact_id}.json"
            if not dry_run:
                write_json(path, epic)
            planned_epic_ids.add(artifact_id)
            created.append({
                "kind": "epic",
                "id": artifact_id,
                "path": str(path),
                "source_work_item_id": item.get("id"),
                "rule": rule.get("name"),
                "dry_run": dry_run,
            })
        if not matched:
            unmatched.append({
                "source_work_item_id": item.get("id"),
                "lane": item.get("lane"),
                "title": item.get("title"),
                "automation_level": item.get("automation_level"),
            })

    return {
        "generated_at": utc_now(),
        "ok": True,
        "enabled": True,
        "dry_run": dry_run,
        "orchestrator_generated_at": orchestrator.get("generated_at"),
        "work_item_count": len(work_items),
        "created_count": len(created),
        "skipped_count": len(skipped),
        "unmatched_count": len(unmatched),
        "created": created,
        "skipped": skipped,
        "unmatched": unmatched,
        "policy_path": str(POLICY_PATH),
        "safety_boundary": SAFETY_BOUNDARY,
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Work Item Materializer",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Enabled: `{report.get('enabled')}`",
        f"- Dry run: `{report.get('dry_run')}`",
        f"- Work items: `{report.get('work_item_count', 0)}`",
        f"- Created: `{report.get('created_count', 0)}`",
        f"- Skipped: `{report.get('skipped_count', 0)}`",
        f"- Unmatched: `{report.get('unmatched_count', 0)}`",
        f"- Safety: {report.get('safety_boundary')}",
        "",
        "## Created",
        "",
    ]
    for item in report.get("created", []):
        lines.append(f"- `{item.get('kind')}` `{item.get('id')}` from `{item.get('source_work_item_id')}` via `{item.get('rule')}`")
    if not report.get("created"):
        lines.append("- No new work items materialized.")
    lines.extend(["", "## Skipped", ""])
    for item in report.get("skipped", [])[:20]:
        lines.append(f"- `{item.get('source_work_item_id')}`: {item.get('reason')} ({item.get('rule')})")
    if not report.get("skipped"):
        lines.append("- None.")
    lines.extend(["", "## Unmatched", ""])
    for item in report.get("unmatched", [])[:20]:
        lines.append(f"- `{item.get('source_work_item_id')}` `{item.get('lane')}`: {item.get('title')}")
    if not report.get("unmatched"):
        lines.append("- None.")
    REPORT_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize JVT orchestrator work items into executable internal tasks/specs.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = materialize(dry_run=args.dry_run)
    write_json(REPORT_JSON_PATH, report)
    write_markdown(report)
    print(json.dumps({
        "ok": report["ok"],
        "dry_run": report.get("dry_run"),
        "work_item_count": report.get("work_item_count", 0),
        "created_count": report.get("created_count", 0),
        "skipped_count": report.get("skipped_count", 0),
        "unmatched_count": report.get("unmatched_count", 0),
        "json_path": str(REPORT_JSON_PATH),
        "markdown_path": str(REPORT_MD_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
