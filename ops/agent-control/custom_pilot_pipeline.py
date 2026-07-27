#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opportunity_qualification import qualify_items


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATE_ROOT = CONTROL_ROOT / "state"
OPS_DB = CONTROL_ROOT / "data" / "jvt_ops.sqlite3"
PACKET_ROOT = REPO_ROOT / "client-work" / "prospect-pilot-packets"
PROPOSAL_ROOT = REPO_ROOT / "client-work" / "proposals"
SOW_ROOT = REPO_ROOT / "client-work" / "statements-of-work"
REPLY_ROOT = REPO_ROOT / "client-work" / "prospect-replies"
PROSPECT_ROOT = REPO_ROOT / "client-work" / "prospects"
SYNTHETIC_ROOT = REPO_ROOT / "client-work" / "synthetic-examples"
REPORT_JSON = STATE_ROOT / "latest-custom-pilot-pipeline.json"
REPORT_MD = STATE_ROOT / "latest-custom-pilot-pipeline.md"

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
            }
        )
    return items


def normalize_opportunity(raw: dict[str, Any]) -> dict[str, Any]:
    service_slug = str(raw.get("service_slug") or "workflow-automation")
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
        "updated_at": raw.get("updated_at") or "",
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
    path = PACKET_ROOT / f"{slugify(name)}-{service_slug}-custom-pilot.md"
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


def write_if_missing(path: Path, content: str) -> tuple[str, bool]:
    if path.exists():
        return str(path), False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return str(path), True


def synthetic_demo_lines(service_slug: str) -> list[str]:
    if service_slug == "ai-voice-intake":
        return [
            "A fictional caller contacts a dental office after hours to request a routine callback. The caller also mentions symptoms, which must be routed to staff without diagnosis or treatment guidance.",
            "",
            "## Review-First Output",
            "",
            "- Caller details and callback number.",
            "- Request category, urgency signals, and preferred callback window.",
            "- A clear statement that the assistant did not diagnose, confirm insurance, or finalize an appointment.",
            "- Staff review packet with the recording/transcript reference and escalation reason.",
        ]
    if service_slug == "workflow-automation":
        return [
            "A fictional housing-complex board meeting produces an agenda, attendee list, ballot checklist, and follow-up requests. Staff need one audit-friendly packet without the agent making election decisions.",
            "",
            "## Review-First Output",
            "",
            "- Meeting and request summary.",
            "- Missing-information and deadline checklist.",
            "- Draft status update for staff review.",
            "- Audit log of inputs, generated drafts, and approval gates.",
        ]
    return [
        "A prospective estate-planning client submits a synthetic intake form, a fictional asset summary, and a draft document checklist. Staff need a fast review packet that identifies what arrived, what is missing, and where each statement came from.",
        "",
        "## Review-First Output",
        "",
        "- Intake summary: fictional household and matter details, clearly labeled as unverified.",
        "- Missing information: three synthetic gaps that staff must resolve.",
        "- Document routing: each uploaded item mapped to the fictional matter checklist.",
        "- Citation trail: every extracted statement tied to the synthetic source and page.",
        "- Human gate: no legal recommendation, deadline, filing, or client-facing answer leaves the system without attorney or staff approval.",
    ]


def followup_draft_lines(item: dict[str, Any], playbook: dict[str, str]) -> list[str]:
    name = str(item.get("account_name") or "there")
    first_name = name.split()[0] if name and name != "Unknown account" else "there"
    source_subject = str(item.get("source_subject") or "").strip()
    subject = source_subject if source_subject.lower().startswith("re:") else f"Re: {playbook['name']} pilot"
    service_slug = str(item.get("service_slug") or "")
    if service_slug == "private-doc-intel":
        body = [
            "Following up with the short example I mentioned. I put together a synthetic version of a private document-review workflow: staff can see what came in, what is missing, and the source behind every drafted point before anything moves forward.",
            "",
            "The first pilot would stay narrow and review-only. No professional decisions, no client-facing output without approval, and no real business data until the handling rules are agreed.",
            "",
            "If that is close to a workflow your team deals with, I can tailor the example around one intake or document-prep process you repeat often.",
        ]
    else:
        body = [
            f"I put together a synthetic {playbook['name'].lower()} example so the workflow can be reviewed before any live data or systems are involved.",
            "",
            "The first pilot would stay narrow, review-first, and limited to one repeated process. Nothing would be sent or decided without the approval gates we agree on.",
            "",
            "If the example is close to the problem your team has, I can tailor it around one real workflow during discovery.",
        ]
    return [
        f"Subject: {subject}",
        "",
        f"Hi {first_name},",
        "",
        *body,
        "",
        "Best,",
        "Chandru",
    ]


def build_conversion_assets(item: dict[str, Any]) -> dict[str, Any]:
    service_slug = str(item.get("service_slug") or "workflow-automation")
    playbook = SERVICE_PLAYBOOKS.get(service_slug, SERVICE_PLAYBOOKS["workflow-automation"])
    name = str(item.get("account_name") or "Qualified prospect")
    slug = slugify(name)
    workspace = PROSPECT_ROOT / slug
    generated = utc_now()

    synthetic_path, synthetic_created = write_if_missing(
        SYNTHETIC_ROOT / f"{slug}-{service_slug}-demo-packet.md",
        "\n".join(
            [
                f"# Synthetic Demo Packet: {name}",
                "",
                f"Generated: `{generated}`",
                "",
                "Status: internal synthetic proof. It contains no client documents, legal advice, or client-specific conclusions.",
                "",
                "## Scenario",
                "",
                *synthetic_demo_lines(service_slug),
                "",
                "## Demo Success Check",
                "",
                "A reviewer can verify the source of every statement, see the missing-data list, edit the packet, and export only after approval.",
            ]
        ),
    )

    proposal_path, proposal_created = write_if_missing(
        PROPOSAL_ROOT / f"{slug}-pilot-proposal.md",
        "\n".join(
            [
                f"# Pilot Proposal Draft: {name}",
                "",
                f"Generated: `{generated}`",
                "",
                "Status: internal draft only. Pricing and terms require operator review before external use.",
                "",
                "## Outcome",
                "",
                "Prove one private, review-first document workflow that reduces repetitive intake or document-preparation work without replacing professional judgment.",
                "",
                "## Proposed Pilot",
                "",
                "- Map one repeated document workflow and its approval boundaries.",
                "- Configure a private workspace using synthetic documents first.",
                "- Produce a cited review packet, missing-information list, and editable draft output.",
                "- Run a short staff validation session and record accepted changes.",
                "",
                "## Commercial Hypothesis",
                "",
                f"- Discovery/source map: {playbook['setup_price']}.",
                f"- Narrow pilot and managed support: {playbook['pilot_price']}.",
                "- Final price depends on document volume, integrations, privacy requirements, and support scope.",
                "",
                "## Boundaries",
                "",
                "- No legal advice or autonomous client communication.",
                "- No real client data until handling, retention, and access rules are approved.",
                "- Every output remains human-reviewed.",
            ]
        ),
    )

    sow_path, sow_created = write_if_missing(
        SOW_ROOT / f"{slug}-draft-sow.md",
        "\n".join(
            [
                f"# Draft Statement Of Work: {name}",
                "",
                f"Generated: `{generated}`",
                "",
                "Status: internal draft only; not an offer or executed agreement.",
                "",
                "## Objective",
                "",
                "Implement and validate one private, citation-backed document workflow using synthetic material before any approved client-data phase.",
                "",
                "## Included",
                "",
                "- one workflow discovery map",
                "- one synthetic source set",
                "- one review packet template",
                "- one human approval checkpoint",
                "- one validation and handoff session",
                "",
                "## Excluded",
                "",
                "- legal judgment or advice",
                "- autonomous client-facing delivery",
                "- broad firm-wide migration",
                "- production integrations not explicitly approved",
                "",
                "## Acceptance",
                "",
                "The pilot is accepted when the agreed synthetic scenario produces a source-cited, editable review packet and all named approval gates work.",
                "",
                "## Fees",
                "",
                "Use the approved proposal after discovery. No price is final in this draft.",
            ]
        ),
    )

    reply_path, reply_created = write_if_missing(
        REPLY_ROOT / f"{slug}-followup-draft.md",
        "\n".join(
            [
                f"# Unsent Follow-Up Draft: {name}",
                "",
                f"Generated: `{generated}`",
                "",
                "Status: review only. Do not send automatically.",
                "",
                *followup_draft_lines(item, playbook),
            ]
        ),
    )

    workspace_readme, workspace_created = write_if_missing(
        workspace / "README.md",
        "\n".join(
            [
                f"# Prospect Workspace: {name}",
                "",
                f"Created: `{generated}`",
                "",
                "Status: qualified prospect; no active client engagement or external commitment.",
                "",
                "## Current Stage",
                "",
                f"- CRM stage: `{item.get('stage') or 'unknown'}`",
                f"- Conversion stage: `{item.get('conversion_stage') or 'qualified'}`",
                f"- Service: {playbook['name']}",
                f"- Contact: `{item.get('contact_email') or 'unknown'}`",
                "",
                "## Required Before Active Client",
                "",
                "- operator-approved follow-up",
                "- discovery answers",
                "- approved scope and price",
                "- signed agreement/SOW",
                "- approved data-handling plan",
            ]
        ),
    )

    acceptance_path, acceptance_created = write_if_missing(
        workspace / "acceptance-checklist.md",
        "\n".join(
            [
                f"# Pilot Acceptance Checklist: {name}",
                "",
                "- [ ] One repeated workflow is confirmed by the prospect.",
                "- [ ] Synthetic source set and expected output are approved.",
                "- [ ] Every output includes source citations.",
                "- [ ] Missing or conflicting information is surfaced.",
                "- [ ] Human approval is required before export or delivery.",
                "- [ ] Data retention and deletion rules are documented.",
                "- [ ] Pilot success metric and price are approved.",
            ]
        ),
    )

    paths = {
        "synthetic_demo": synthetic_path,
        "proposal": proposal_path,
        "draft_sow": sow_path,
        "unsent_followup": reply_path,
        "prospect_workspace": workspace_readme,
        "acceptance_checklist": acceptance_path,
    }
    created = [
        key
        for key, was_created in {
            "synthetic_demo": synthetic_created,
            "proposal": proposal_created,
            "draft_sow": sow_created,
            "unsent_followup": reply_created,
            "prospect_workspace": workspace_created,
            "acceptance_checklist": acceptance_created,
        }.items()
        if was_created
    ]
    return {
        "account_name": name,
        "conversion_stage": item.get("conversion_stage"),
        "paths": paths,
        "created": created,
        "ready": all(Path(path).exists() for path in paths.values()),
    }


def build_report() -> dict[str, Any]:
    opportunities = [normalize_opportunity(item) for item in fetch_opportunities()]
    decisions = pending_pilot_decisions()
    items = qualify_items(opportunities + decisions, REPO_ROOT)
    qualified = [item for item in items if item.get("qualified")]
    concepts = [
        item
        for item in items
        if not item.get("duplicate") and item.get("qualification_status") == "concept"
    ]
    excluded = [
        item
        for item in items
        if not item.get("duplicate")
        and item.get("qualification_status") in {"internal", "disqualified", "unqualified", "inactive"}
    ]
    duplicates = [item for item in items if item.get("duplicate")]
    qualified.sort(key=lambda value: (priority(value), str(value.get("account_name") or "")))
    packet_paths = [write_packet(item) for item in qualified[:8]]
    conversions = [build_conversion_assets(item) for item in qualified[:3]]
    service_counts: dict[str, int] = {}
    for item in qualified:
        service = str(item.get("service_slug") or "unknown")
        service_counts[service] = service_counts.get(service, 0) + 1
    return {
        "generated_at": utc_now(),
        "ok": True,
        "warm_count": len(qualified),
        "qualified_count": len(qualified),
        "concept_count": len(concepts),
        "excluded_count": len(excluded),
        "duplicate_count": len(duplicates),
        "packet_count": len(packet_paths),
        "conversion_ready_count": sum(1 for item in conversions if item.get("ready")),
        "service_counts": service_counts,
        "packet_paths": packet_paths,
        "conversion_assets": conversions,
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
            for index, item in enumerate(qualified[:8])
        ],
        "guardrail": "Internal custom-pilot planning only. No external reply, provider action, credential request, live data processing, or commitment is authorized by this report.",
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Custom Pilot Pipeline",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Qualified external opportunities: `{report['qualified_count']}`",
        f"- Concepts awaiting a real contact: `{report['concept_count']}`",
        f"- Excluded records: `{report['excluded_count']}`",
        f"- Duplicate records: `{report['duplicate_count']}`",
        f"- Pilot packets refreshed: `{report['packet_count']}`",
        f"- Conversion workspaces ready: `{report['conversion_ready_count']}`",
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
    lines.extend(["", "## Conversion Assets", ""])
    conversions = report.get("conversion_assets") or []
    if not conversions:
        lines.append("- No qualified external opportunity is ready for conversion assets.")
    for conversion in conversions:
        lines.append(
            f"- `{conversion.get('account_name')}` ready=`{str(bool(conversion.get('ready'))).lower()}` "
            f"created={','.join(conversion.get('created') or []) or 'none'}"
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
    print(
        json.dumps(
            {
                "ok": True,
                "qualified_count": report["qualified_count"],
                "concept_count": report["concept_count"],
                "packet_count": report["packet_count"],
                "conversion_ready_count": report["conversion_ready_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
