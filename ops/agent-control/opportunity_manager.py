#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
OPS_DB = CONTROL_ROOT / "data" / "jvt_ops.sqlite3"
REPORT_JSON = STATE_ROOT / "latest-opportunity-manager.json"
REPORT_MD = STATE_ROOT / "latest-opportunity-manager.md"

ACTIVE_STAGES = {
    "inbound-hit-needs-review",
    "reply-needs-response",
    "proposal-needed",
    "pilot-discovery-needed",
    "active",
}

WARM_STAGES = ACTIVE_STAGES | {
    "reply-sent-awaiting-next",
}

STAGE_ORDER = {
    "reply-needs-response": 0,
    "inbound-hit-needs-review": 1,
    "proposal-needed": 2,
    "pilot-discovery-needed": 3,
    "reply-sent-awaiting-next": 4,
    "active": 4,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def source_payload(source: str) -> dict[str, Any]:
    if not source:
        return {}
    path = Path(source)
    if not path.exists() or path.suffix.lower() != ".json":
        return {}
    return load_json(path, {})


def contact_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].strip().lower()


def next_action(item: dict[str, Any]) -> str:
    stage = str(item.get("stage") or "")
    service = str(item.get("service_slug") or "")
    if stage == "inbound-hit-needs-review":
        if service == "ai-voice-intake":
            return "Draft a short human-reviewed reply with 3 dental/voice-intake discovery questions and a dry-run demo offer."
        if service == "workflow-automation":
            return "Draft a discovery reply focused on one workflow map, one synthetic example, and one narrow pilot scope."
        return "Draft a short human-reviewed reply; do not place the contact into generic no-reply followups."
    if stage == "reply-needs-response":
        return "Prepare the next reviewed response and keep all automation from sending a generic follow-up."
    if stage == "proposal-needed":
        return "Prepare a one-page pilot proposal with scope, price hypothesis, boundaries, and next meeting ask."
    if stage == "pilot-discovery-needed":
        return "Schedule or draft a discovery packet; collect current process, data sensitivity, approval points, and success metric."
    if stage == "reply-sent-awaiting-next":
        return "Keep this as a warm protected opportunity; prepare a custom pilot packet and do not send generic no-reply follow-ups."
    if stage == "active":
        return "Keep delivery state current and create the next internal task before responding externally."
    return "Review stage and decide whether this should be active, closed, or converted into a pilot task."


def priority(item: dict[str, Any]) -> int:
    base = STAGE_ORDER.get(str(item.get("stage") or ""), 9)
    service = str(item.get("service_slug") or "")
    if service in {"ai-voice-intake", "workflow-automation"}:
        return base
    return base + 1


def fetch_items() -> list[dict[str, Any]]:
    if not OPS_DB.exists():
        return []
    conn = sqlite3.connect(OPS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
          o.id,
          o.service_slug,
          o.stage,
          o.source,
          o.notes,
          o.created_at,
          o.updated_at,
          a.name AS account_name,
          a.website,
          a.industry,
          a.city_state,
          sc.name AS service_name,
          (
            SELECT email
            FROM contacts c
            WHERE c.account_id = a.id AND COALESCE(c.email, '') <> ''
            ORDER BY
              CASE
                WHEN c.email LIKE 'hello@%' THEN 0
                WHEN c.email LIKE 'info@%' THEN 1
                WHEN c.email LIKE 'contact@%' THEN 2
                WHEN c.email LIKE 'office@%' THEN 3
                ELSE 4
              END,
              c.updated_at DESC
            LIMIT 1
          ) AS contact_email
        FROM opportunities o
        JOIN accounts a ON a.id = o.account_id
        LEFT JOIN service_catalog sc ON sc.slug = o.service_slug
        ORDER BY
          CASE o.stage
            WHEN 'reply-needs-response' THEN 0
            WHEN 'inbound-hit-needs-review' THEN 1
            WHEN 'proposal-needed' THEN 2
            WHEN 'pilot-discovery-needed' THEN 3
            WHEN 'reply-sent-awaiting-next' THEN 4
            WHEN 'active' THEN 4
            ELSE 9
          END,
          o.updated_at DESC
        """
    ).fetchall()
    conn.close()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload = source_payload(str(item.get("source") or ""))
        item["source_subject"] = payload.get("subject") or payload.get("summary") or ""
        item["source_snippet"] = payload.get("snippet") or payload.get("body_preview") or ""
        item["source_from"] = payload.get("from") or payload.get("sender") or ""
        item["active"] = item.get("stage") in ACTIVE_STAGES
        item["warm"] = item.get("stage") in WARM_STAGES
        item["contact_domain"] = contact_domain(str(item.get("contact_email") or ""))
        item["next_action"] = next_action(item)
        item["priority"] = priority(item)
        items.append(item)
    items.sort(key=lambda value: (int(value.get("priority") or 9), str(value.get("updated_at") or "")), reverse=False)
    return items


def build_report() -> dict[str, Any]:
    items = fetch_items()
    active = [item for item in items if item.get("active")]
    warm = [item for item in items if item.get("warm")]
    response_needed = [
        item
        for item in active
        if item.get("stage") in {"reply-needs-response", "inbound-hit-needs-review", "proposal-needed", "pilot-discovery-needed"}
    ]
    protected_domains = sorted({item["contact_domain"] for item in warm if item.get("contact_domain")})
    return {
        "generated_at": utc_now(),
        "ok": True,
        "db_path": str(OPS_DB),
        "opportunity_count": len(items),
        "active_count": len(active),
        "warm_count": len(warm),
        "response_needed_count": len(response_needed),
        "protected_contact_domains": protected_domains,
        "items": items[:25],
        "top_next_actions": [
            {
                "account_name": item.get("account_name"),
                "service_name": item.get("service_name") or item.get("service_slug"),
                "stage": item.get("stage"),
                "contact_email": item.get("contact_email"),
                "next_action": item.get("next_action"),
            }
            for item in response_needed[:5]
        ],
        "guardrail": "Active hits must not receive generic no-reply followups. Draft replies and pilot material are human-reviewed before external send.",
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Opportunity Manager",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Opportunities: `{report['opportunity_count']}`",
        f"- Active: `{report['active_count']}`",
        f"- Warm/protected: `{report.get('warm_count', 0)}`",
        f"- Need response/review: `{report['response_needed_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "## Top Next Actions",
        "",
    ]
    top = report.get("top_next_actions") or []
    if not top:
        lines.append("- No active opportunity responses are pending.")
    for item in top:
        lines.append(
            f"- `{item.get('stage')}` {item.get('account_name') or 'Unknown'}"
            f" / {item.get('service_name') or 'Service TBD'}: {item.get('next_action')}"
        )
    lines.extend(["", "## Active Opportunities", ""])
    active_items = [item for item in report.get("items", []) if item.get("active")]
    if not active_items:
        lines.append("- None.")
    for item in active_items:
        lines.extend([
            f"### {item.get('account_name') or 'Unknown account'}",
            "",
            f"- Stage: `{item.get('stage')}`",
            f"- Service: `{item.get('service_name') or item.get('service_slug')}`",
            f"- Contact: `{item.get('contact_email') or 'unknown'}`",
            f"- Source: `{item.get('source') or 'unknown'}`",
            f"- Notes: {item.get('notes') or item.get('source_snippet') or 'No notes.'}",
            f"- Next: {item.get('next_action')}",
            "",
        ])
    lines.extend(["", "## Warm Protected Opportunities", ""])
    warm_items = [item for item in report.get("items", []) if item.get("warm") and not item.get("active")]
    if not warm_items:
        lines.append("- None.")
    for item in warm_items:
        lines.extend([
            f"### {item.get('account_name') or 'Unknown account'}",
            "",
            f"- Stage: `{item.get('stage')}`",
            f"- Service: `{item.get('service_name') or item.get('service_slug')}`",
            f"- Contact: `{item.get('contact_email') or 'unknown'}`",
            f"- Source: `{item.get('source') or 'unknown'}`",
            f"- Next: {item.get('next_action')}",
            "",
        ])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    write_json(REPORT_JSON, report)
    write_markdown(report)
    print(json.dumps({"ok": report["ok"], "active_count": report["active_count"], "response_needed_count": report["response_needed_count"]}))


if __name__ == "__main__":
    main()
