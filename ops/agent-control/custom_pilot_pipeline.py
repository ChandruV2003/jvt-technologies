#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
OPS_DB = CONTROL_ROOT / "data" / "jvt_ops.sqlite3"
PACKET_ROOT = REPO_ROOT / "client-work" / "prospect-pilot-packets"
REPORT_JSON = STATE_ROOT / "latest-custom-pilot-pipeline.json"
REPORT_MD = STATE_ROOT / "latest-custom-pilot-pipeline.md"

WARM_STAGES = {
    "inbound-hit-needs-review",
    "reply-needs-response",
    "proposal-needed",
    "pilot-discovery-needed",
    "reply-sent-awaiting-next",
    "active",
}

SERVICE_PLAYBOOKS = {
    "ai-voice-intake": {
        "name": "AI Receptionist / Voice Intake",
        "pilot_price": "$750-$1,500 dry-run pilot; $300-$900/mo managed support",
        "setup_price": "$500-$1,000 discovery/script map",
        "first_step": "Collect call categories, escalation rules, no-say rules, phone-system constraints, and one synthetic scenario pack.",
        "proof_asset": "Dental/local-office missed-call intake demo with staff-review packet.",
    },
    "workflow-automation": {
        "name": "Agentic Workflow Automation",
        "pilot_price": "$2,500-$7,500 narrow pilot; $500-$2,000/mo managed support",
        "setup_price": "$500-$1,500 workflow map",
        "first_step": "Map one repeated workflow, approval gates, systems of record, sensitive data, and one safe synthetic example.",
        "proof_asset": "Board/ballot or operations-request packet with checklist, draft status email, and audit log.",
    },
    "private-doc-intel": {
        "name": "Private Document / Knowledge Assistant",
        "pilot_price": "$1,500-$5,000 narrow document workflow; $300-$1,500/mo managed support",
        "setup_price": "$500-$1,500 source/document map",
        "first_step": "Pick one document-heavy lookup workflow and define approved source material plus answer boundaries.",
        "proof_asset": "Citation-backed answer packet from synthetic documents.",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_slug() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "prospect"


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


def fetch_opportunities() -> list[dict[str, Any]]:
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
          sc.name AS service_name,
          (
            SELECT email
            FROM contacts c
            WHERE c.account_id = a.id AND COALESCE(c.email, '') <> ''
            ORDER BY c.updated_at DESC
            LIMIT 1
          ) AS contact_email
        FROM opportunities o
        JOIN accounts a ON a.id = o.account_id
        LEFT JOIN service_catalog sc ON sc.slug = o.service_slug
        ORDER BY o.updated_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def pending_pilot_decisions() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted((CONTROL_ROOT / "pending").glob("*.json")):
        payload = load_json(path, {})
        if payload.get("type") != "pilot_next_step_decision":
            continue
        service = str(payload.get("service_line") or "").lower()
        if "voice" in service or "receptionist" in service:
            service_slug = "ai-voice-intake"
        elif "ballot" in service or "workflow" in service:
            service_slug = "workflow-automation"
        else:
            service_slug = "workflow-automation"
        items.append(
            {
                "kind": "pilot_decision",
                "id": payload.get("id") or path.stem,
                "account_name": payload.get("target_customer") or payload.get("service_line") or path.stem,
                "contact_email": "",
                "website": "",
                "service_slug": service_slug,
                "service_name": SERVICE_PLAYBOOKS.get(service_slug, {}).get("name", service_slug),
                "stage": "pilot-discovery-needed",
                "source": str(path),
                "notes": payload.get("recommended_next_step") or payload.get("offer") or "",
                "pricing_hypothesis": payload.get("pricing_hypothesis") or "",
                "pain": payload.get("pain") or "",
                "target_customer": payload.get("target_customer") or "",
                "major_risks": payload.get("major_risks") or [],
                "warm": True,
            }
        )
    return items


def normalize_opportunity(raw: dict[str, Any]) -> dict[str, Any]:
    service_slug = str(raw.get("service_slug") or "workflow-automation")
    text = " ".join(
        str(raw.get(key) or "").lower()
        for key in ("account_name", "industry", "service_slug", "service_name", "notes", "source")
    )
    if any(term in text for term in ("document workflow", "law firm", "legal", "attorney", "elder law", "estate", "probate")):
        service_slug = "private-doc-intel"
    if service_slug not in SERVICE_PLAYBOOKS:
        service_slug = "workflow-automation"
    stage = str(raw.get("stage") or "")
    return {
        "kind": "opportunity",
        "id": raw.get("id"),
        "account_name": raw.get("account_name") or "Unknown account",
        "contact_email": raw.get("contact_email") or "",
        "website": raw.get("website") or "",
        "service_slug": service_slug,
        "service_name": SERVICE_PLAYBOOKS[service_slug]["name"],
        "stage": stage,
        "source": raw.get("source") or "",
        "notes": raw.get("notes") or "",
        "pricing_hypothesis": "",
        "pain": raw.get("notes") or "",
        "target_customer": raw.get("account_name") or "",
        "major_risks": [],
        "warm": stage in WARM_STAGES,
    }


def priority(item: dict[str, Any]) -> int:
    stage = str(item.get("stage") or "")
    if stage in {"reply-needs-response", "inbound-hit-needs-review", "proposal-needed"}:
        return 1
    if item.get("kind") == "pilot_decision":
        return 2
    if stage == "pilot-discovery-needed":
        return 2
    if stage == "reply-sent-awaiting-next":
        return 3
    return 5


def response_template(item: dict[str, Any]) -> str:
    service_slug = str(item.get("service_slug") or "workflow-automation")
    playbook = SERVICE_PLAYBOOKS.get(service_slug, SERVICE_PLAYBOOKS["workflow-automation"])
    if service_slug == "ai-voice-intake":
        return "\n".join(
            [
                "Subject: Small voice-intake pilot idea",
                "",
                "Hi {{contact_name_or_team}},",
                "",
                "We can keep this narrow: one disclosed AI intake flow that collects caller details, request type, urgency, and callback info, then gives staff a clean review packet.",
                "",
                "Before building anything live, I would start with a dry-run using synthetic calls. The only things I need first are:",
                "",
                "1. the top 3 call types you want handled",
                "2. what the assistant must never say or decide",
                "3. where staff should receive the review packet",
                "4. whether the first pilot should be after-hours only or all missed calls",
                "",
                f"Pilot shape: {playbook['setup_price']} first, then {playbook['pilot_price']}.",
                "",
                "If that sounds useful, I can send a one-page workflow map and a sample intake packet before we talk live.",
                "",
                "Chandru",
            ]
        )
    if service_slug == "private-doc-intel":
        return "\n".join(
            [
                "Subject: Small document-workflow pilot",
                "",
                "Hi {{contact_name_or_team}},",
                "",
                "I would keep the first version very narrow: one private document workflow where the system helps staff find the right internal source, produce a cited draft answer or checklist, and leave final judgment with your team.",
                "",
                "Before building anything real, I would use synthetic documents and map one repeat workflow:",
                "",
                "1. what question or task repeats most often",
                "2. which approved documents/templates should be searchable",
                "3. what the assistant must never answer on its own",
                "4. who reviews the output before it leaves the firm",
                "5. what a useful sample packet should look like",
                "",
                f"Pilot shape: {playbook['setup_price']} first, then {playbook['pilot_price']}.",
                "",
                "If useful, I can send a one-page workflow map and a synthetic example packet so you can see the shape before sharing any real material.",
                "",
                "Chandru",
            ]
        )
    return "\n".join(
        [
            "Subject: Narrow workflow pilot",
            "",
            "Hi {{contact_name_or_team}},",
            "",
            "The best first step is not a giant AI platform. It is one workflow that repeats often enough to be worth cleaning up.",
            "",
            "I would start by mapping one process end-to-end, then build a review-first agent that creates the packet, checklist, draft status update, and audit trail while leaving decisions with your team.",
            "",
            "The first discovery pass needs:",
            "",
            "1. the workflow you repeat the most",
            "2. the documents/templates already used",
            "3. what must stay human-approved",
            "4. what data is sensitive",
            "5. what would count as a successful pilot",
            "",
            f"Pilot shape: {playbook['setup_price']} first, then {playbook['pilot_price']}.",
            "",
            "If useful, I can mock this up with synthetic data first so there is no risk to live client or ballot data.",
            "",
            "Chandru",
        ]
    )


def write_packet(item: dict[str, Any]) -> str:
    service_slug = str(item.get("service_slug") or "workflow-automation")
    playbook = SERVICE_PLAYBOOKS.get(service_slug, SERVICE_PLAYBOOKS["workflow-automation"])
    name = str(item.get("account_name") or item.get("service_name") or "prospect")
    path = PACKET_ROOT / f"{today_slug()}-{slugify(name)}-{service_slug}-custom-pilot.md"
    lines = [
        f"# Custom Pilot Packet: {name}",
        "",
        f"Generated: `{utc_now()}`",
        "",
        "Status: internal draft only. Do not send externally, promise delivery, request credentials, connect providers, process real customer data, or quote final terms without operator approval.",
        "",
        "## Opportunity",
        "",
        f"- Source: `{item.get('source') or 'manual/warm lead'}`",
        f"- Stage: `{item.get('stage') or 'unknown'}`",
        f"- Service: {playbook['name']}",
        f"- Contact: `{item.get('contact_email') or 'unknown'}`",
        f"- Website: `{item.get('website') or 'unknown'}`",
        "",
        "## Why This Is Higher Probability",
        "",
        "This is a custom-but-repeatable path: solve the prospect's specific workflow, keep the first pilot narrow, then reuse the underlying intake, packet, approval, notification, and QA modules for similar clients.",
        "",
        "## Pain / Context",
        "",
        str(item.get("pain") or item.get("notes") or "Needs discovery before the pain can be stated safely."),
        "",
        "## First Paid Pilot Shape",
        "",
        f"- Discovery/setup: {playbook['setup_price']}",
        f"- Pilot/retainer hypothesis: {playbook['pilot_price']}",
        f"- First step: {playbook['first_step']}",
        f"- Proof asset: {playbook['proof_asset']}",
        "",
        "## Scope Boundaries",
        "",
        "- Use synthetic data first.",
        "- Keep every output review-first.",
        "- Do not connect live systems until data handling and approval gates are signed off.",
        "- Do not make legal, medical, insurance, election, financial, or scheduling decisions.",
        "- Treat pricing as a hypothesis until the workflow is scoped.",
        "",
        "## Discovery Questions",
        "",
        "1. What is the exact workflow that repeats every week?",
        "2. What inputs start the workflow?",
        "3. What output does staff currently create?",
        "4. What must a human approve before anything goes out?",
        "5. What data is sensitive or should be excluded from the first pilot?",
        "6. What would make the pilot worth paying for after two weeks?",
        "",
        "## Draft Reply",
        "",
        "```text",
        response_template(item),
        "```",
        "",
        "## Next Internal Action",
        "",
        "Prepare a synthetic demo packet matching this workflow, then ask for approval before sending the draft reply or scheduling a live discovery call.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def build_report() -> dict[str, Any]:
    opportunities = [normalize_opportunity(item) for item in fetch_opportunities()]
    decisions = pending_pilot_decisions()
    items = [item for item in opportunities + decisions if item.get("warm") or item.get("kind") == "pilot_decision"]
    items.sort(key=lambda value: (priority(value), str(value.get("account_name") or "")))
    packet_paths = [write_packet(item) for item in items[:8]]
    service_counts: dict[str, int] = {}
    for item in items:
        service = str(item.get("service_slug") or "unknown")
        service_counts[service] = service_counts.get(service, 0) + 1
    return {
        "generated_at": utc_now(),
        "ok": True,
        "warm_count": len(items),
        "packet_count": len(packet_paths),
        "service_counts": service_counts,
        "packet_paths": packet_paths,
        "items": items[:25],
        "next_actions": [
            {
                "account_name": item.get("account_name"),
                "service": item.get("service_name"),
                "stage": item.get("stage"),
                "priority": priority(item),
                "next_action": SERVICE_PLAYBOOKS.get(str(item.get("service_slug") or ""), SERVICE_PLAYBOOKS["workflow-automation"])["first_step"],
                "packet_path": packet_paths[index] if index < len(packet_paths) else "",
            }
            for index, item in enumerate(items[:8])
        ],
        "guardrail": "Internal custom-pilot planning only. No external reply, provider action, credential request, live data processing, or commitment is authorized by this report.",
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Custom Pilot Pipeline",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Warm/custom opportunities: `{report['warm_count']}`",
        f"- Pilot packets refreshed: `{report['packet_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "## Focus",
        "",
        "Prioritize custom-but-repeatable pilots for companies that already show interest or have a clear workflow pain. Cold outreach supports these wedges; it does not replace them.",
        "",
        "## Next Actions",
        "",
    ]
    if not report.get("next_actions"):
        lines.append("- No warm/custom pilot actions are currently staged.")
    for action in report.get("next_actions") or []:
        lines.append(
            f"- P{action.get('priority')} `{action.get('stage')}` {action.get('account_name')} / {action.get('service')}: {action.get('next_action')} Packet: `{action.get('packet_path')}`"
        )
    lines.extend(["", "## Service Counts", ""])
    for service, count in sorted((report.get("service_counts") or {}).items()):
        lines.append(f"- `{service}`: {count}")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    report = build_report()
    write_json(REPORT_JSON, report)
    write_markdown(report)
    print(json.dumps({"ok": True, "warm_count": report["warm_count"], "packet_count": report["packet_count"]}))


if __name__ == "__main__":
    main()
