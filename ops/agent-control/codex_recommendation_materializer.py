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
EPIC_ROOT = CONTROL_ROOT / "epics"
RESULT_PATH = STATE_ROOT / "latest-codex-escalation-result.json"
ESCALATION_PATH = STATE_ROOT / "latest-codex-escalation.json"
REPORT_JSON = STATE_ROOT / "latest-codex-recommendation-materializer.json"
REPORT_MD = STATE_ROOT / "latest-codex-recommendation-materializer.md"

EPIC_DIRS = ("queued", "running", "done", "blocked", "held")
PATH_RE = re.compile(
    r"(?:(?:ops|outreach|products|site|strategy|lead-pipeline|client-work|tests)/"
    r"[A-Za-z0-9_.@+~/-]+\.py)"
)
SAFETY_BOUNDARY = (
    "Repository-scoped internal implementation only. No external outreach delivery, packet approval, "
    "spending, account changes, market orders, crypto custody/network participation, public posting, "
    "provider enablement, destructive broad file actions, or external commitments."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def recommendation_payload() -> tuple[dict[str, Any], str]:
    result = load_json(RESULT_PATH)
    escalation = load_json(ESCALATION_PATH)
    latest = escalation.get("latest_result") if isinstance(escalation.get("latest_result"), dict) else {}
    final_messages: list[str] = []
    action_messages: list[str] = []
    for source in (result, latest):
        for key in ("final_message", "summary"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                final_messages.append(value.strip())
        action_items = source.get("action_items")
        if isinstance(action_items, list):
            action_messages.extend(str(item).strip() for item in action_items if str(item).strip())
    # Summarized action items may normalize identifiers (for example, removing
    # underscores). Prefer the verbatim final message whenever it is available.
    messages = final_messages or action_messages
    text = "\n\n".join(dict.fromkeys(messages))
    metadata = {
        "generated_at": result.get("generated_at") or latest.get("generated_at"),
        "task_id": result.get("task_id") or latest.get("task_id"),
        "model": result.get("model") or latest.get("model"),
        "ok": result.get("ok") if "ok" in result else latest.get("ok"),
    }
    return metadata, text


def referenced_paths(text: str) -> list[str]:
    return sorted(
        {
            match.group(0).rstrip(".,:;)")
            for match in PATH_RE.finditer(text)
            if ".." not in Path(match.group(0)).parts
        }
    )


def recommendation_fingerprint(metadata: dict[str, Any], text: str, paths: list[str]) -> str:
    basis = json.dumps(
        {
            "task_id": metadata.get("task_id"),
            "generated_at": metadata.get("generated_at"),
            "paths": paths,
            "text": re.sub(r"\s+", " ", text).strip()[:12000],
        },
        sort_keys=True,
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def existing_epic(epic_id: str) -> tuple[str, Path] | None:
    for directory in EPIC_DIRS:
        path = EPIC_ROOT / directory / f"{epic_id}.json"
        if path.exists():
            return directory, path
    return None


def build_epic(
    *,
    epic_id: str,
    metadata: dict[str, Any],
    recommendation: str,
    scope_paths: list[str],
    missing_paths: list[str],
) -> dict[str, Any]:
    return {
        "id": epic_id,
        "title": f"Implement Codex recommendation {epic_id.rsplit('-', 1)[-1]}",
        "created_at": utc_now(),
        "queued_by": "codex_recommendation_materializer",
        "status": "queued",
        "level": "epic",
        "feature": "company-autonomy",
        "model_tier": "codex-cli-capped",
        "model": "gpt-5.5",
        "execution_mode": "codex_workspace_write",
        "codex_enabled": True,
        "requires_approval": False,
        "source_codex_recommendation": metadata,
        "story": recommendation[:14000],
        "scope_paths": scope_paths,
        "deliverables": missing_paths or scope_paths,
        "acceptance_criteria": [
            "Implement the smallest safe repository-scoped version of the recommendation.",
            "Reuse existing JVT patterns and remove contradictory duplicate logic where the recommendation requires it.",
            "Add or update focused tests for changed behavior.",
            "Run syntax checks and targeted dry-run validation.",
            "Do not send outreach, approve packets, call providers, spend money, trade, publish, or make external commitments.",
            "Return changed files, validation results, and any exact blocker through architect-inbox.",
        ],
        "roi_case": {
            "revenue_goal_link": "Removes a measured JVT pipeline blocker on the path to the March 2027 $10k cash-flow goal.",
            "expected_business_value": "Turns repeated diagnosis into durable implementation and reduces idle outreach capacity.",
            "why_codex_is_worth_it": "The recommendation spans multiple repository workflows and needs coherent code changes plus validation.",
            "success_metric": "Named implementation files exist, focused validation passes, and Egg stops repeating the same recommendation.",
            "fallback_if_not_run": "Keep the recommendation tracked and continue safe local analysis without consuming another duplicate Codex call.",
        },
        "requested_external_actions": [],
        "safety_boundary": SAFETY_BOUNDARY,
        "timeout_seconds": 1800,
    }


def materialize(*, dry_run: bool) -> dict[str, Any]:
    metadata, recommendation = recommendation_payload()
    paths = referenced_paths(recommendation)
    missing = [path for path in paths if not (REPO_ROOT / path).is_file()]
    report: dict[str, Any] = {
        "generated_at": utc_now(),
        "ok": True,
        "dry_run": dry_run,
        "source": metadata,
        "referenced_paths": paths,
        "missing_paths": missing,
        "safety_boundary": SAFETY_BOUNDARY,
    }
    if not recommendation:
        report.update({"status": "no_recommendation", "materialized": False})
        return report
    if not paths:
        report.update({"status": "no_repository_python_paths", "materialized": False})
        return report
    fingerprint = recommendation_fingerprint(metadata, recommendation, paths)
    epic_id = f"codex-recommendation-{fingerprint}"
    report["fingerprint"] = fingerprint
    report["epic_id"] = epic_id
    existing = existing_epic(epic_id)
    if existing:
        directory, path = existing
        report.update(
            {
                "status": f"tracked_{directory}",
                "materialized": False,
                "epic_path": str(path),
                "next_action": "Do not repeat this Codex ask; follow the existing epic through architect-inbox.",
            }
        )
        return report

    epic = build_epic(
        epic_id=epic_id,
        metadata=metadata,
        recommendation=recommendation,
        scope_paths=paths,
        missing_paths=missing,
    )
    epic_path = EPIC_ROOT / "queued" / f"{epic_id}.json"
    if not dry_run:
        write_json(epic_path, epic)
    report.update(
        {
            "status": "would_queue" if dry_run else "queued",
            "materialized": not dry_run,
            "epic_path": str(epic_path),
            "next_action": "Let the capped epic agent implement this once; suppress duplicate read-only Codex asks meanwhile.",
        }
    )
    return report


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Codex Recommendation Materializer",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report.get('status')}`",
        f"- Materialized: `{report.get('materialized')}`",
        f"- Source task: `{(report.get('source') or {}).get('task_id')}`",
        f"- Epic: `{report.get('epic_id') or ''}`",
        f"- Guardrail: {report['safety_boundary']}",
        "",
        "## Referenced Paths",
        "",
    ]
    lines.extend(f"- `{path}`" for path in report.get("referenced_paths", []))
    if not report.get("referenced_paths"):
        lines.append("- None.")
    lines.extend(["", "## Missing Paths", ""])
    lines.extend(f"- `{path}`" for path in report.get("missing_paths", []))
    if not report.get("missing_paths"):
        lines.append("- None.")
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or "No action."), ""])
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Turn a new Codex code recommendation into one deduplicated, capped implementation epic."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = materialize(dry_run=args.dry_run)
    write_json(REPORT_JSON, report)
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "status": report.get("status"),
                "materialized": report.get("materialized"),
                "epic_id": report.get("epic_id"),
                "missing_path_count": len(report.get("missing_paths") or []),
                "report": str(REPORT_JSON),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
