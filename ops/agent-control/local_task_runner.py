#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
TASK_ROOT = CONTROL_ROOT / "tasks"
STATE_ROOT = CONTROL_ROOT / "state"
LOCK_PATH = STATE_ROOT / "local-task-runner.lock"
AUTOTRADER_ROOT = Path("/Users/c.s.d.v.r.s./Developer/JVT-AutoTrader")
CODEX_CLI = Path("/Applications/Codex.app/Contents/Resources/codex")
ASSIGNMENT_POLICY_PATH = CONTROL_ROOT / "policies" / "agent-assignment-policy.json"

TASK_DIRS = ("pending", "running", "completed", "failed", "held")

DISALLOWED_WORDS = {
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

DEFAULT_ASSIGNMENT_POLICY = {
    "default_assignment": {
        "level": "task",
        "feature": "general-ops",
        "model_tier": "deterministic",
        "self_review": "standard",
    },
    "task_type_assignments": {},
    "codex_cli": {
        "allowed_level": "epic",
        "note": "Local runner must not invoke Codex CLI. It can only report escalation need into epic specs.",
    },
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


def load_assignment_policy() -> dict[str, Any]:
    policy = load_json(ASSIGNMENT_POLICY_PATH, {})
    if not isinstance(policy, dict):
        return DEFAULT_ASSIGNMENT_POLICY
    merged = json.loads(json.dumps(DEFAULT_ASSIGNMENT_POLICY))
    for key, value in policy.items():
        if key == "task_type_assignments" and isinstance(value, dict):
            merged["task_type_assignments"].update(value)
        elif key == "default_assignment" and isinstance(value, dict):
            merged["default_assignment"].update(value)
        else:
            merged[key] = value
    return merged


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def today_slug() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def ensure_dirs() -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in TASK_DIRS:
        (TASK_ROOT / name).mkdir(parents=True, exist_ok=True)


def task_text(task: dict[str, Any]) -> str:
    return json.dumps(task, sort_keys=True).lower()


def contains_disallowed_phrase(text: str, phrase: str) -> bool:
    escaped = re.escape(phrase).replace(r"\ ", r"\s+")
    pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def hold_reason(task: dict[str, Any]) -> str | None:
    text = task_text(task)
    if task.get("requires_approval"):
        return "Task declares requires_approval=true."
    for word in sorted(DISALLOWED_WORDS):
        if contains_disallowed_phrase(text, word):
            return f"Task text contains approval-gated/disallowed phrase: {word}"
    return None


def task_assignment(task: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    task_type = str(task.get("type") or "")
    default = policy.get("default_assignment") if isinstance(policy.get("default_assignment"), dict) else {}
    assignments = policy.get("task_type_assignments") if isinstance(policy.get("task_type_assignments"), dict) else {}
    typed = assignments.get(task_type) if isinstance(assignments.get(task_type), dict) else {}
    assignment = {**default, **typed}
    level = str(task.get("level") or assignment.get("level") or "task")
    feature = str(task.get("feature") or task.get("lane") or assignment.get("feature") or "general-ops")
    model_tier = str(task.get("model_tier") or assignment.get("model_tier") or "deterministic")
    self_review = str(task.get("self_review") or assignment.get("self_review") or "standard")
    return {
        "level": level,
        "feature": feature,
        "story_id": task.get("story_id") or task.get("id") or "",
        "task_type": task_type,
        "owner": "local-task-runner",
        "model_tier": model_tier,
        "self_review": self_review,
        "codex_cli_allowed": level == "epic",
        "codex_cli_policy": (policy.get("codex_cli") or {}).get("policy_file") if isinstance(policy.get("codex_cli"), dict) else "",
    }


def artifact_exists(raw_path: str) -> bool:
    if not raw_path:
        return True
    path = Path(raw_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.exists()


def self_review_task_result(task: dict[str, Any], result: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    task_type = str(task.get("type") or "")
    if assignment.get("codex_cli_allowed"):
        findings.append({
            "severity": "fail",
            "code": "codex_cli_wrong_lane",
            "detail": "Local task runner cannot execute epic/Codex CLI work; create an epic-agent spec instead.",
        })
    if not result.get("ok"):
        findings.append({
            "severity": "fail",
            "code": "handler_not_ok",
            "detail": "Handler returned ok=false.",
        })
    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    for step in steps:
        if isinstance(step, dict) and step.get("ok") is False:
            findings.append({
                "severity": "fail",
                "code": "step_failed",
                "detail": f"{step.get('name') or 'step'} returned ok=false.",
            })
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
    for artifact in artifacts:
        if not artifact_exists(str(artifact)):
            findings.append({
                "severity": "warn",
                "code": "artifact_missing",
                "detail": str(artifact),
            })
    if not result.get("guardrail"):
        findings.append({
            "severity": "warn",
            "code": "missing_guardrail",
            "detail": "Handler did not return an explicit safety guardrail.",
        })
    if any(contains_disallowed_phrase(json.dumps(result, sort_keys=True).lower(), word) for word in sorted(DISALLOWED_WORDS)):
        findings.append({
            "severity": "fail",
            "code": "result_contains_disallowed_phrase",
            "detail": "Result text contains an approval-gated phrase.",
        })
    strict = str(assignment.get("self_review") or "") == "strict"
    blocking_findings = [item for item in findings if item.get("severity") == "fail" or (strict and item.get("severity") == "warn" and item.get("code") == "artifact_missing")]
    return {
        "ok": not blocking_findings,
        "reviewed_at": utc_now(),
        "reviewer": "local-task-runner-self-review",
        "task_type": task_type,
        "assignment": assignment,
        "finding_count": len(findings),
        "blocking_finding_count": len(blocking_findings),
        "findings": findings,
        "policy": "deterministic result, step, artifact, and safety-boundary review. Codex CLI is reserved for epic-agent only.",
    }


def run_command(name: str, command: list[str], cwd: Path = REPO_ROOT, timeout: int = 120) -> dict[str, Any]:
    started = time.time()
    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "name": name,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "duration_ms": int((time.time() - started) * 1000),
        "stdout_tail": result.stdout.strip().splitlines()[-12:],
        "stderr_tail": result.stderr.strip().splitlines()[-12:],
    }


def report_script(task_name: str, script_name: str, timeout: int = 90) -> dict[str, Any]:
    return run_command(task_name, ["python3", f"ops/agent-control/{script_name}"], timeout=timeout)


def refresh_growth_state(_task: dict[str, Any]) -> dict[str, Any]:
    steps = [
        run_command("venture_pipeline", ["python3", "ops/agent-control/venture_pipeline.py"], timeout=60),
        run_command("orchestrator", ["python3", "ops/agent-control/orchestrator.py"], timeout=60),
        run_command("eom_agent", ["python3", "ops/agent-control/eom_agent.py"], timeout=60),
        run_command("agent_interop_check", ["python3", "ops/agent-control/agent_interop_check.py"], timeout=60),
    ]
    return {
        "ok": all(step["ok"] for step in steps),
        "steps": steps,
        "artifacts": [
            str(STATE_ROOT / "latest-venture-pipeline.md"),
            str(STATE_ROOT / "latest-orchestrator.md"),
            str(STATE_ROOT / "latest-eom-brief.md"),
            str(STATE_ROOT / "latest-agent-interop.md"),
        ],
    }


def codex_cli_version_snapshot(_task: dict[str, Any]) -> dict[str, Any]:
    steps = []
    if CODEX_CLI.exists():
        steps.append(run_command("codex_version", [str(CODEX_CLI), "--version"], timeout=30))
    else:
        steps.append({"name": "codex_version", "ok": False, "reason": f"Missing {CODEX_CLI}"})
    steps.append(run_command("python_version", ["python3", "--version"], timeout=30))
    steps.append(run_command("node_version", ["/opt/homebrew/bin/node", "--version"], timeout=30))
    path = STATE_ROOT / "latest-local-runtime-snapshot.json"
    payload = {"generated_at": utc_now(), "steps": steps, "ok": all(step.get("ok") for step in steps)}
    write_json(path, payload)
    return {"ok": payload["ok"], "steps": steps, "artifacts": [str(path)]}


def content_backlog_from_assets(_task: dict[str, Any]) -> dict[str, Any]:
    ideas = [
        {
            "source": "site/ai-receptionist-intake-demo.html",
            "title": "Missed calls should not become mystery voicemails",
            "format": "YouTube Short / Instagram Reel",
            "status": "packet-drafted",
            "next_step": "Review strategy/content-ops/ai-receptionist-content-packet-2026-06-11.md before any post.",
        },
        {
            "source": "site/meeting-to-action-demo.html",
            "title": "Stop losing action items after client calls",
            "format": "YouTube Short / Instagram Reel",
            "status": "ready-for-packet-draft",
            "next_step": "Draft review-only script/caption/thumbnail brief from the meeting demo.",
        },
        {
            "source": "strategy/workflow-maps/jvt-lead-to-followup-flow.md",
            "title": "What a real automation workflow map looks like",
            "format": "Carousel / short explainer",
            "status": "ready-for-packet-draft",
            "next_step": "Create before/after visual outline; no posting without approval.",
        },
        {
            "source": "strategy/venture-scout/2026-06-11-insurance-coi-service-request-triage.md",
            "title": "COI requests are workflow problems, not AI chatbot problems",
            "format": "Founder note / short explainer",
            "status": "ready-for-packet-draft",
            "next_step": "Turn the insurance triage scout into a proof-asset brief first.",
        },
    ]
    path = REPO_ROOT / "strategy" / "content-ops" / "content-idea-backlog.md"
    lines = [
        "# JVT Content Idea Backlog",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: internal planning only. No posting or API publishing is authorized from this file.",
        "",
    ]
    for index, idea in enumerate(ideas, start=1):
        lines.extend([
            f"## {index}. {idea['title']}",
            "",
            f"- Source: `{idea['source']}`",
            f"- Format: {idea['format']}",
            f"- Status: `{idea['status']}`",
            f"- Next step: {idea['next_step']}",
            "",
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)], "idea_count": len(ideas)}


def meeting_to_action_content_packet(_task: dict[str, Any]) -> dict[str, Any]:
    path = REPO_ROOT / "strategy" / "content-ops" / f"meeting-to-action-content-packet-{today_slug()}.md"
    lines = [
        "# Content Ops Packet: Meeting-To-Action Demo",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: review-only. Do not post, schedule, upload, or connect platform APIs without approval.",
        "",
        "Source asset: `site/meeting-to-action-demo.html`",
        "",
        "## Content Goal",
        "",
        "Show the concrete business outcome: calls and meetings should produce reviewed tasks, owner assignments, missing-info lists, and client-ready follow-up drafts.",
        "",
        "Hook:",
        "",
        "> Meetings are not done when the call ends. They are done when the next actions are captured.",
        "",
        "## YouTube Shorts Script",
        "",
        "Length target: 35-45 seconds",
        "",
        "Visual direction: dark JVT page, split screen between messy meeting notes and a clean action packet. Avoid robot imagery.",
        "",
        "Script:",
        "",
        "> Most teams do not lose work because nobody talked about it.",
        ">",
        "> They lose work because the call ends and the next steps scatter across memory, notes, email, and chat.",
        ">",
        "> This JVT demo turns a meeting into a reviewed action packet.",
        ">",
        "> Decisions. Owners. Due dates. Missing information. Draft follow-up.",
        ">",
        "> A real person still reviews it before anything goes out.",
        ">",
        "> The value is simple: fewer forgotten tasks, cleaner client follow-up, and less admin drag after every meeting.",
        "",
        "On-screen text:",
        "",
        "- \"Meeting -> action packet\"",
        "- \"Owners\"",
        "- \"Due dates\"",
        "- \"Missing info\"",
        "- \"Human review before send\"",
        "",
        "## Instagram Reel Caption",
        "",
        "A meeting is not finished just because the call ended.",
        "",
        "The useful output is a reviewed packet:",
        "",
        "- decisions",
        "- task owners",
        "- due dates",
        "- missing information",
        "- draft follow-up",
        "",
        "That is the JVT meeting-to-action wedge: turn client calls into structured next steps without pretending the system should make business decisions on its own.",
        "",
        "## Thumbnail / Cover Brief",
        "",
        "Text:",
        "",
        "> Stop losing action items after client calls.",
        "",
        "Visual:",
        "",
        "- dark JVT background",
        "- messy notes/card stack on left",
        "- clean action packet on right",
        "- use current teal/blue/warm accent palette",
        "- no generic AI face, brain, or robot icon",
        "",
        "## Approval Checklist",
        "",
        "- Use only synthetic meeting material.",
        "- Do not claim autonomous client communication.",
        "- Keep legal, tax, financial, insurance, and medical advice boundaries explicit when relevant.",
        "- Mention human review before any follow-up is sent.",
        "- Link to the public demo only after final review.",
        "- Do not publish until operator approves exact copy and platform.",
        "",
        "## Next Step",
        "",
        "Record one short demo walkthrough and manually review it before any platform upload or API automation.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)]}


def insurance_coi_proof_asset(_task: dict[str, Any]) -> dict[str, Any]:
    path = REPO_ROOT / "client-work" / "synthetic-examples" / f"insurance-coi-triage-proof-{today_slug()}.md"
    lines = [
        "# Synthetic Proof Asset: Insurance COI Request Triage",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: synthetic internal proof. Do not present as a real client deployment.",
        "",
        "## Scenario",
        "",
        "A commercial client emails an agency asking for a certificate of insurance for a landlord and needs it today.",
        "",
        "## Synthetic Incoming Email",
        "",
        "From: `operations@example-contractor.test`",
        "",
        "Subject: `Need COI for new job site today`",
        "",
        "Body:",
        "",
        "> Hi, can you send a certificate of insurance to the property manager for our new job at 100 Market Street? They need general liability and workers comp listed. Certificate holder is Market Street Holdings LLC, 100 Market Street, Newark, NJ 07102. Please send it to certificates@example-property.test and copy me. We need it today if possible.",
        "",
        "## Extracted Fields For Staff Review",
        "",
        "| Field | Extracted Value | Review Status |",
        "| --- | --- | --- |",
        "| Request type | Certificate of insurance | Needs licensed/staff review |",
        "| Insured/client | Example Contractor | Needs account match |",
        "| Certificate holder | Market Street Holdings LLC | Review |",
        "| Holder address | 100 Market Street, Newark, NJ 07102 | Review |",
        "| Coverage requested | General liability, workers compensation | Review policy availability |",
        "| Delivery recipient | certificates@example-property.test | Review recipient |",
        "| Client copy | operations@example-contractor.test | Review |",
        "| Urgency | Today | Review feasibility |",
        "",
        "## Missing-Information Checklist",
        "",
        "- Confirm account/client identity.",
        "- Confirm active policies and carrier rules.",
        "- Confirm whether any special wording, additional insured, waiver, or endorsement is required.",
        "- Confirm certificate holder spelling and address.",
        "- Confirm approved delivery recipient.",
        "",
        "## Staff Task Packet",
        "",
        "Task title: `Review COI request for Example Contractor - Market Street Holdings`",
        "",
        "Assigned role: licensed CSR / account manager",
        "",
        "Priority: same-day",
        "",
        "Recommended next action: review policy and certificate requirements before issuing anything.",
        "",
        "## Draft Client Response For Human Review",
        "",
        "> Thanks. We received the COI request for Market Street Holdings LLC. We are reviewing the account and certificate requirements now. If the property manager requires special wording, additional insured language, or waiver wording, please forward those instructions so our team can review them before issuing.",
        "",
        "## Boundaries",
        "",
        "- JVT does not issue COIs.",
        "- JVT does not bind, alter, advise on, or confirm coverage.",
        "- The workflow only extracts, routes, drafts, and logs material for staff review.",
        "- Agency staff remain responsible for policy review and final communication.",
        "",
        "## Sales Use",
        "",
        "This proof asset supports a narrow paid pilot: one intake inbox, one request type, review-only packets, no AMS writeback until trust is proven.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)]}


def it_ballot_workflow_pilot_brief(_task: dict[str, Any]) -> dict[str, Any]:
    path = REPO_ROOT / "client-work" / "pilot-briefs" / f"it-ballot-services-agentic-workflow-pilot-{today_slug()}.md"
    lines = [
        "# Pilot Brief: IT / Ballot Services Agentic Workflow System",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: internal planning brief. Do not contact the prospect, request credentials, process real ballots, or make service commitments from this file.",
        "",
        "## Target Customer",
        "",
        "An IT consulting / AV operations company that supports housing-complex board meetings and provides third-party ballot/election-process services.",
        "",
        "## Pain / Demand",
        "",
        "- Meeting logistics create repeated admin work before, during, and after board meetings.",
        "- Ballot/election support likely involves deadlines, checklists, eligibility files, notices, forms, status tracking, and audit-sensitive documentation.",
        "- Staff need fewer manual reminders, cleaner packets, and safer review workflows without replacing human control over election-sensitive decisions.",
        "",
        "## Proposed Offer",
        "",
        "A review-first agentic operations layer for repeatable meeting and ballot-service workflows.",
        "",
        "Initial paid pilot scope:",
        "",
        "1. Intake agent: converts incoming client requests into structured job packets.",
        "2. Meeting-prep agent: builds agenda/checklist/task packets for AV and board-meeting logistics.",
        "3. Ballot-process checklist agent: tracks milestone checklists, required documents, deadlines, missing items, and staff-review status.",
        "4. Document-generation agent: drafts notices, instruction sheets, status emails, meeting summaries, and internal task lists from approved templates.",
        "5. Audit-log agent: records what was generated, who reviewed it, what changed, and what was sent.",
        "",
        "## Hard Boundaries",
        "",
        "- Do not process live ballots in an autonomous black box.",
        "- Do not determine eligibility, winners, vote validity, quorum, or legal compliance.",
        "- Do not send election-related notices or results without human approval.",
        "- Do not store unnecessary PII; use least-privilege access and explicit retention rules.",
        "- Treat every output as draft/review-required until the prospect defines their compliance process.",
        "",
        "## Agent Workflow Sketch",
        "",
        "```text",
        "Request received",
        "  -> Intake classifier",
        "  -> Job packet",
        "  -> Missing-info checklist",
        "  -> Human review",
        "  -> Template/document draft",
        "  -> Human approval",
        "  -> Audit log + status board update",
        "```",
        "",
        "## Pricing Hypothesis",
        "",
        "- Discovery/workflow map: $500-$1,500 fixed fee.",
        "- Narrow pilot build: $2,500-$7,500 depending on integrations and templates.",
        "- Managed AI operations retainer: $500-$2,000/month for monitoring, prompt/template updates, QA, and workflow changes.",
        "",
        "## Delivery Complexity",
        "",
        "Medium-high. The admin automation is straightforward, but ballot/election-adjacent workflows are sensitive and require strict human review, audit trails, permission controls, and careful language.",
        "",
        "## Major Risks",
        "",
        "- Legal/compliance ambiguity around housing-complex election processes.",
        "- PII and voter/owner eligibility data handling.",
        "- Prospect may use custom spreadsheets, PDFs, email inboxes, or legacy tools with messy data.",
        "- Any hallucinated deadline/result/instruction could create serious trust issues.",
        "- Scope can sprawl into a full election-management platform if not constrained.",
        "",
        "## Next Validation Step",
        "",
        "Run a 45-minute workflow-discovery call using synthetic examples only. Capture:",
        "",
        "- top three repeated workflows",
        "- documents/templates they already use",
        "- systems of record",
        "- what humans must approve",
        "- what data is sensitive",
        "- current turnaround time and bottlenecks",
        "- one pilot workflow that can be tested without live election data",
        "",
        "## First Demo To Build",
        "",
        "Use a synthetic board-meeting/election-support request and generate:",
        "",
        "- intake summary",
        "- required-info checklist",
        "- staff task board",
        "- draft client status email",
        "- audit log entry",
        "",
        "This should be presented as operational workflow automation, not as an autonomous election decision system.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)]}


def dental_voice_intake_pilot_brief(_task: dict[str, Any]) -> dict[str, Any]:
    path = REPO_ROOT / "client-work" / "pilot-briefs" / f"dental-voice-intake-pilot-{today_slug()}.md"
    lines = [
        "# Pilot Brief: Dental Office AI Voice Intake",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: internal planning brief. Do not contact the prospect, enable live calls, connect paid phone-provider usage, process real patient data, or make service commitments from this file.",
        "",
        "## Target Customer",
        "",
        "A small dental office or specialty practice that receives scheduling, insurance, callback, and after-hours urgency calls.",
        "",
        "## Pain / Demand",
        "",
        "- Staff spend time collecting repeated details from callers.",
        "- After-hours voicemails are often incomplete.",
        "- New-patient, reschedule, insurance, and urgent-pain calls need different routing.",
        "- Call notes need to be clear enough for staff to review without the AI making medical or scheduling commitments.",
        "",
        "## Proposed Offer",
        "",
        "A disclosed AI voice intake assistant that captures structured call packets for staff review.",
        "",
        "Initial paid pilot scope:",
        "",
        "1. Intake script: one question at a time, short, human-sounding, explicitly AI-disclosed.",
        "2. Routing classifier: new patient, existing patient, reschedule, insurance question, urgent symptom, billing/admin, other.",
        "3. Staff review packet: caller name, callback number, request type, urgency flag, preferred windows, insurance carrier name if volunteered, and transcript summary.",
        "4. Safety handoff: no diagnosis, no medication advice, no final scheduling, no coverage confirmation.",
        "5. QA loop: review call packets weekly and adjust prompts/scripts.",
        "",
        "## Hard Boundaries",
        "",
        "- Do not give dental, medical, medication, or emergency advice.",
        "- Do not confirm insurance coverage.",
        "- Do not book, cancel, or reschedule final appointments unless the office explicitly approves a controlled workflow later.",
        "- Do not expose patient records or imply access to patient history.",
        "- Keep the assistant disclosed as AI-assisted.",
        "- Keep all real call handling disabled until provider, compliance, and operator approval gates are cleared.",
        "",
        "## Agent Workflow Sketch",
        "",
        "```text",
        "Inbound call",
        "  -> AI disclosure",
        "  -> request type + caller details",
        "  -> urgency/safety boundary check",
        "  -> staff-review packet",
        "  -> notification / dashboard item",
        "  -> human callback or action",
        "```",
        "",
        "## Voice Quality Notes",
        "",
        "- Use Chandru-approved voice samples only as internal style references.",
        "- Do not replay raw samples directly as responses.",
        "- Tune for natural cadence, quick turn-taking, and minimal filler.",
        "- One or two natural pauses/fillers can mask latency, but the goal is fast, concise conversation.",
        "- Tone should adapt to caller context: warmer for anxious/urgent callers, concise for scheduling/admin calls.",
        "",
        "## Pricing Hypothesis",
        "",
        "- Discovery/script map: $500-$1,000 fixed fee.",
        "- Dry-run pilot build: $750-$1,500 fixed fee.",
        "- Managed support: $300-$900/month depending on call volume, QA, and provider costs.",
        "",
        "## Delivery Complexity",
        "",
        "Medium. The intake workflow is achievable, but live phone latency, disclosure, provider cost, and patient-data expectations need careful gating.",
        "",
        "## Major Risks",
        "",
        "- Patient privacy expectations and health-adjacent communication.",
        "- Caller may ask for medical advice.",
        "- Latency or synthetic voice quality may reduce trust.",
        "- Phone-provider/live-call costs can grow with usage.",
        "- Office may expect scheduling-system integration too early.",
        "",
        "## Next Validation Step",
        "",
        "Collect prospect-specific workflow details before official outreach:",
        "",
        "- office name and contact",
        "- call categories they want handled",
        "- after-hours expectations",
        "- existing scheduling/phone system",
        "- what the AI must never say",
        "- what staff needs in the review packet",
        "- how quickly staff responds to urgent items",
        "",
        "## First Demo To Build",
        "",
        "Use synthetic BrightPath-style calls and generate:",
        "",
        "- new patient cleaning request packet",
        "- existing patient reschedule packet",
        "- urgent pain after-hours packet with safety handoff",
        "- staff notification example",
        "- dashboard review view",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)]}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def priority_packet_review_queue(_task: dict[str, Any]) -> dict[str, Any]:
    source = REPO_ROOT / "strategy" / "prospect-lists" / "priority-packet-candidates-2026-06-10.csv"
    rows = read_csv_rows(source)
    path = REPO_ROOT / "strategy" / "prospect-packet-prep" / f"priority-review-queue-{today_slug()}.md"
    lines = [
        "# Priority Packet Review Queue",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: internal queue staging only. This is not approval to send.",
        "",
        f"Source: `{source.relative_to(REPO_ROOT)}`",
        "",
        "## Queue Rules",
        "",
        "- Re-verify the public recipient before any packet becomes send-ready.",
        "- Reject placeholders, suspicious scraped addresses, unrelated personal addresses, mismatched domains, and generic page-title company names.",
        "- Confirm no recent reply, suppression, or same-thread conflict.",
        "- Keep each message tied to one concrete workflow pain.",
        "- Do not send from this file.",
        "",
    ]
    if not rows:
        lines.append("No priority rows were available.")
    for index, row in enumerate(rows, start=1):
        lines.extend([
            f"## {index}. {row.get('company_name', 'Unknown')}",
            "",
            f"- Offer lane: {row.get('offer_lane', '')}",
            f"- Website: {row.get('website', '')}",
            f"- Candidate recipient: `{row.get('public_email', '')}`",
            f"- Current status: `{row.get('current_status', '')}`",
            f"- Why selected: {row.get('why_selected', '')}",
            f"- Required review before send: {row.get('required_review_before_send', '')}",
            f"- Next packet action: {row.get('next_packet_action', '')}",
            "",
            "Packet stance:",
            "",
            "- One narrow paid-pilot ask.",
            "- Human review remains explicit.",
            "- Avoid broad \"AI transformation\" language.",
            "- Include only the relevant proof asset/demo link after final review.",
            "",
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)], "candidate_count": len(rows)}


def inbox_triage_brief(_task: dict[str, Any]) -> dict[str, Any]:
    inbox_root = REPO_ROOT / "outreach" / "inbox" / "new"
    items = sorted(inbox_root.glob("*/*.json")) if inbox_root.exists() else []
    path = REPO_ROOT / "strategy" / "inbox-triage" / f"inbox-triage-brief-{today_slug()}.md"
    lines = [
        "# Inbox Triage Brief",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: internal review only. This file does not authorize external replies, follow-ups, sends, commitments, provider usage, or account changes.",
        "",
        f"New inbox items: `{len(items)}`",
        "",
    ]
    if not items:
        lines.append("No new inbox items were present.")
    for index, item_path in enumerate(items, start=1):
        item = load_json(item_path, {})
        snippet = str(item.get("snippet") or "").replace("\r", " ").replace("\n", " ").strip()
        if len(snippet) > 650:
            snippet = snippet[:650].rstrip() + "..."
        lines.extend([
            f"## {index}. {item.get('subject', item_path.stem)}",
            "",
            f"- File: `{item_path.relative_to(REPO_ROOT)}`",
            f"- From: {item.get('from', '')}",
            f"- To: {item.get('to', '')}",
            f"- Date: {item.get('date', '')}",
            f"- Sender domain: `{item.get('sender_domain', '')}`",
            f"- Triage bucket: `{item.get('triage_bucket', '')}`",
            f"- Triage priority: `{item.get('triage_priority', '')}`",
            f"- Triage action: `{item.get('triage_action', '')}`",
            f"- Triage reason: {item.get('triage_reason', '')}",
            "",
            "Snippet:",
            "",
            f"> {snippet}",
            "",
            "Recommended internal next step:",
            "",
            "- Draft a short human-reviewed response if this is a real prospect or partner signal.",
            "- Keep unrelated outbound separate; do not include this contact in generic no-reply follow-up automation.",
            "- Mark the item reviewed or closed only after the human response decision is captured.",
            "",
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)], "item_count": len(items)}


def outreach_review_queue_brief(_task: dict[str, Any]) -> dict[str, Any]:
    review_root = REPO_ROOT / "outreach" / "queue" / "review"
    packet_paths = sorted(review_root.glob("*.json")) if review_root.exists() else []
    packets: list[tuple[Path, dict[str, Any]]] = []
    initial_packets: list[tuple[Path, dict[str, Any]]] = []
    followup_packets: list[tuple[Path, dict[str, Any]]] = []
    for packet_path in packet_paths:
        packet = load_json(packet_path, {})
        packets.append((packet_path, packet))
        target = followup_packets if packet.get("follow_up_stage") or packet.get("follow_up_parent_stem") else initial_packets
        target.append((packet_path, packet))

    path = REPO_ROOT / "strategy" / "prospect-packet-prep" / f"outreach-review-queue-brief-{today_slug()}.md"
    lines = [
        "# Outreach Review Queue Brief",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: internal QA only. This file does not approve packets or authorize external delivery.",
        "",
        f"- Review packets: `{len(packet_paths)}`",
        f"- Initial packets: `{len(initial_packets)}`",
        f"- Follow-up packets: `{len(followup_packets)}`",
        "",
        "## Review Rules",
        "",
        "- Prefer public business inboxes or relevant owner, partner, or operations contacts.",
        "- Reject placeholders, unrelated personal addresses, scraped-looking addresses, mismatched domains, and generic page-title company names.",
        "- Keep active inbox hits out of generic follow-up automation.",
        "- Approve only after recipient quality and offer fit are both checked.",
        "",
        "## First 30 Items To Review",
        "",
    ]
    for index, (packet_path, packet) in enumerate(packets[:30], start=1):
        kind = "follow-up" if packet.get("follow_up_stage") or packet.get("follow_up_parent_stem") else "initial"
        lines.extend([
            f"### {index}. {packet.get('company_name', packet_path.stem)}",
            "",
            f"- Kind: `{kind}`",
            f"- File: `{packet_path.relative_to(REPO_ROOT)}`",
            f"- Recipient: `{packet.get('recipient_email', '')}`",
            f"- Subject: {packet.get('subject', '')}",
            f"- Industry: {packet.get('industry', '')}",
            f"- Offer: {packet.get('personalized_offer', '')}",
            f"- Fit score: `{packet.get('fit_score', '')}`",
            f"- Contact page: {packet.get('contact_page', '')}",
            f"- Current status: `{packet.get('status', '')}`",
            "",
            "QA decision needed:",
            "",
            "- recipient quality",
            "- company/domain match",
            "- service-line fit",
            "- copy tone",
            "- whether to approve, revise, or reject",
            "",
        ])
    if not packets:
        lines.append("No review packets were present.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "ok": True,
        "artifacts": [str(path)],
        "review_count": len(packet_paths),
        "initial_count": len(initial_packets),
        "followup_count": len(followup_packets),
    }


def followup_review_brief(_task: dict[str, Any]) -> dict[str, Any]:
    review_root = REPO_ROOT / "outreach" / "queue" / "review"
    followups: list[tuple[Path, dict[str, Any]]] = []
    for packet_path in sorted(review_root.glob("*.json")) if review_root.exists() else []:
        packet = load_json(packet_path, {})
        if packet.get("follow_up_stage") or packet.get("follow_up_parent_stem"):
            followups.append((packet_path, packet))

    path = REPO_ROOT / "strategy" / "prospect-packet-prep" / f"followup-review-brief-{today_slug()}.md"
    lines = [
        "# Follow-Up Review Brief",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: internal QA only. No follow-up is approved or delivered from this file.",
        "",
        f"Follow-up packets in review: `{len(followups)}`",
        "",
        "## Review Priorities",
        "",
        "- Confirm there is no real reply or suppression on the thread.",
        "- Confirm the recipient is still a valid business contact.",
        "- Keep the wording short, practical, and not needy.",
        "- Reject anything tied to an active inbox hit until the human reply path is decided.",
        "",
    ]
    for index, (packet_path, packet) in enumerate(followups[:25], start=1):
        lines.extend([
            f"## {index}. {packet.get('company_name', packet_path.stem)}",
            "",
            f"- File: `{packet_path.relative_to(REPO_ROOT)}`",
            f"- Recipient: `{packet.get('recipient_email', '')}`",
            f"- Subject: {packet.get('subject', '')}",
            f"- Parent packet: `{packet.get('follow_up_parent_stem', '')}`",
            f"- Parent sent at: `{packet.get('parent_sent_at', '')}`",
            f"- Stage: `{packet.get('follow_up_stage', '')}`",
            f"- Offer: {packet.get('personalized_offer', '')}",
            "",
        ])
    if not followups:
        lines.append("No follow-up packets are currently in review.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)], "followup_count": len(followups)}


def offer_segment_summary(_task: dict[str, Any]) -> dict[str, Any]:
    sources = [
        REPO_ROOT / "strategy" / "prospect-lists" / "ai-receptionist-intake-targets.csv",
        REPO_ROOT / "strategy" / "prospect-lists" / "meeting-to-action-targets.csv",
    ]
    path = REPO_ROOT / "strategy" / "prospect-lists" / f"offer-segment-review-{today_slug()}.md"
    lines = [
        "# Offer Segment Review",
        "",
        f"Generated: {utc_now()}",
        "",
        "Status: internal segmentation only. This is not a send list.",
        "",
    ]
    total = 0
    for source in sources:
        rows = read_csv_rows(source)
        total += len(rows)
        status_counts: dict[str, int] = {}
        for row in rows:
            key = row.get("lead_status") or row.get("verification_status") or "unknown"
            status_counts[key] = status_counts.get(key, 0) + 1
        lines.extend([
            f"## {source.name}",
            "",
            f"- Rows: `{len(rows)}`",
            f"- Source: `{source.relative_to(REPO_ROOT)}`",
            "",
            "Status mix:",
            "",
        ])
        if status_counts:
            for status, count in sorted(status_counts.items()):
                lines.append(f"- `{status}`: {count}")
        else:
            lines.append("- No rows available.")
        lines.extend(["", "Top review candidates:", ""])
        for row in rows[:5]:
            company = row.get("company_name", "Unknown")
            fit = row.get("offer_fit", "").strip()
            next_step = row.get("next_step", "").strip()
            lines.append(f"- {company}: {fit} Next: {next_step}")
        lines.append("")
    lines.extend([
        "## Next Validation Action",
        "",
        "Use this summary to decide which offer lane gets the next manually reviewed packet batch. Do not treat any row as send-ready until recipient quality is re-verified.",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)], "row_count": total}


def ten_k_execution_digest(_task: dict[str, Any]) -> dict[str, Any]:
    path = REPO_ROOT / "strategy" / "venture-outputs" / f"{today_slug()}-10k-execution-digest.md"
    venture = load_json(STATE_ROOT / "latest-venture-pipeline.json", {})
    eom = load_json(STATE_ROOT / "latest-eom-brief.json", {})
    runner = load_json(STATE_ROOT / "latest-local-task-runner.json", {})
    lines = [
        "# JVT $10k Execution Digest",
        "",
        f"Generated: {utc_now()}",
        "",
        "Target: `$10,000 gross cash collected by 2027-03-31`",
        "",
        "## Current Operating Thesis",
        "",
        "The fastest path remains service-led: sell narrow paid pilots using proof assets, then attach monthly managed support. Trading, mining, tokens, hardware, and franchise ideas stay research-only until their risk-adjusted math beats one more paid service pilot.",
        "",
        "## What The Agents Should Push Next",
        "",
        "1. Convert demo/proof assets into review-only packet material.",
        "2. Re-verify recipients before anything enters a send-ready queue.",
        "3. Keep follow-ups active; no-reply is a queue state, not a conclusion.",
        "4. Refresh paper trading as research only.",
        "5. Generate one new venture scout or proof asset per day.",
        "",
        "## Latest Machine State",
        "",
        f"- Venture pipeline status: `{venture.get('status', 'unknown')}`",
        f"- Ranked opportunities: `{venture.get('summary', {}).get('opportunity_count', 'unknown')}`",
        f"- Top opportunity: `{venture.get('summary', {}).get('top_opportunity', 'unknown')}`",
        f"- EOM generated: `{eom.get('generated_at', 'unknown')}`",
        f"- Local runner pending remaining: `{runner.get('pending_remaining', 'unknown')}`",
        "",
        "## Approval-Gated Actions",
        "",
        "- Prospect email sends",
        "- Social posting or platform API publishing",
        "- Paid tools, ads, domains, franchise fees, or vendor applications",
        "- Live trading, fund movement, wallets, mining, or staking",
        "",
        "## Next Manual Decision",
        "",
        "Pick the first paid-pilot offer to push hardest this week: AI receptionist/intake, meeting-to-action packets, or insurance service-request triage.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)]}


def venture_scout_index(_task: dict[str, Any]) -> dict[str, Any]:
    source_dir = REPO_ROOT / "strategy" / "venture-scout"
    path = REPO_ROOT / "strategy" / "venture-scout" / "INDEX.md"
    reports = sorted(source_dir.glob("*.md")) if source_dir.exists() else []
    lines = [
        "# Venture Scout Index",
        "",
        f"Generated: {utc_now()}",
        "",
    ]
    if reports:
        for report in reports:
            title = report.read_text(encoding="utf-8", errors="ignore").splitlines()[0].lstrip("# ").strip()
            lines.append(f"- [{title}]({report.name})")
    else:
        lines.append("- No venture scout reports found.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "artifacts": [str(path)], "report_count": len(reports)}


def paper_trader_refresh(_task: dict[str, Any]) -> dict[str, Any]:
    if not AUTOTRADER_ROOT.exists():
        return {"ok": False, "reason": f"Missing {AUTOTRADER_ROOT}"}
    steps = [
        run_command("check_account", [".venv/bin/python", "scripts/check_account.py"], cwd=AUTOTRADER_ROOT, timeout=120),
        run_command("run_paper_bot", [".venv/bin/python", "scripts/run_paper_bot.py"], cwd=AUTOTRADER_ROOT, timeout=120),
        run_command("backtest_etf_signals", [".venv/bin/python", "scripts/backtest_etf_signals.py"], cwd=AUTOTRADER_ROOT, timeout=180),
    ]
    return {
        "ok": all(step["ok"] for step in steps),
        "steps": steps,
        "artifacts": [
            str(AUTOTRADER_ROOT / "state" / "latest_account_snapshot.json"),
            str(AUTOTRADER_ROOT / "state" / "latest_paper_bot_report.json"),
            str(AUTOTRADER_ROOT / "state" / "latest_backtest.json"),
        ],
        "guardrail": "Paper-only scripts. No --execute-paper and no live endpoint actions.",
    }


def paper_trader_health(_task: dict[str, Any]) -> dict[str, Any]:
    step = report_script("paper_trader_health", "paper_trader_health.py")
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(STATE_ROOT / "latest-paper-trader-health.json"),
            str(STATE_ROOT / "latest-paper-trader-health.md"),
        ],
        "guardrail": "Read-only paper-trader health summary. No order execution.",
    }


def model_router_status(_task: dict[str, Any]) -> dict[str, Any]:
    step = run_command("model_router_status", ["python3", "ops/agent-control/model_router.py", "status"], timeout=20)
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [str(STATE_ROOT / "latest-model-router.json")],
        "guardrail": "Internal status check only. No model downloads or paid calls.",
    }


def codex_escalation_status(_task: dict[str, Any]) -> dict[str, Any]:
    step = run_command("codex_escalation_status", ["python3", "ops/agent-control/codex_escalation_runner.py", "status"], timeout=20)
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [str(STATE_ROOT / "latest-codex-escalation.json")],
        "guardrail": "Status only. Does not execute Codex or spend credits.",
    }


def jvt_ops_db_sync(_task: dict[str, Any]) -> dict[str, Any]:
    step = run_command("jvt_ops_db_sync", ["python3", "ops/agent-control/jvt_ops_db.py", "sync"], timeout=120)
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(CONTROL_ROOT / "data" / "jvt_ops.sqlite3"),
            str(STATE_ROOT / "latest-jvt-ops-db.json"),
            str(STATE_ROOT / "latest-jvt-ops-db.md"),
        ],
        "guardrail": "Internal database sync only. No external sends or provider actions.",
    }


def voice_quality_sample_inventory(_task: dict[str, Any]) -> dict[str, Any]:
    voice_root = REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "jvt-inbound-voice-agent" / "voice-quality"
    samples_root = voice_root / "samples"
    renders_root = voice_root / "renders"
    scorecards_root = voice_root / "scorecards"
    script_pack = voice_root / "scripts" / "chandru-style-script-pack.json"

    metadata_paths = sorted(samples_root.glob("*.json")) if samples_root.exists() else []
    audio_suffixes = (".webm", ".wav", ".m4a", ".ogg", ".flac", ".mp3")
    script_data = load_json(script_pack, {"scripts": []})
    expected_scripts = {str(item.get("id") or ""): item for item in script_data.get("scripts", []) if isinstance(item, dict)}
    samples: list[dict[str, Any]] = []
    seen_script_ids: set[str] = set()

    for meta_path in metadata_paths:
        meta = load_json(meta_path, {})
        script_id = str(meta.get("script_id") or meta_path.stem)
        seen_script_ids.add(script_id)
        audio_path = None
        for suffix in audio_suffixes:
            candidate = meta_path.with_suffix(suffix)
            if candidate.exists():
                audio_path = candidate
                break
        browser_settings = meta.get("browser_audio_settings") if isinstance(meta.get("browser_audio_settings"), dict) else {}
        samples.append({
            "script_id": script_id,
            "title": meta.get("script_title") or expected_scripts.get(script_id, {}).get("title") or meta_path.stem,
            "category": meta.get("script_category") or expected_scripts.get(script_id, {}).get("category") or "",
            "recorded_at": meta.get("recorded_at"),
            "input_device": meta.get("input_device"),
            "content_type": meta.get("content_type"),
            "sample_rate": browser_settings.get("sampleRate") or browser_settings.get("sample_rate"),
            "channel_count": browser_settings.get("channelCount") or browser_settings.get("channel_count"),
            "audio_path": str(audio_path) if audio_path else "",
            "audio_bytes": audio_path.stat().st_size if audio_path else 0,
            "metadata_path": str(meta_path),
            "has_audio": bool(audio_path),
        })

    missing_script_ids = sorted(script_id for script_id in expected_scripts if script_id and script_id not in seen_script_ids)
    render_files = sorted(path for path in renders_root.glob("*") if path.is_file()) if renders_root.exists() else []
    tool_checks = {
        "afinfo": bool(shutil.which("afinfo")),
        "afconvert": bool(shutil.which("afconvert")),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
    }
    python_modules = {}
    for module in ("numpy", "soundfile", "librosa", "torch", "torchaudio", "whisper", "TTS", "coqui_tts"):
        python_modules[module] = importlib.util.find_spec(module) is not None

    generated_at = utc_now()
    scorecards_root.mkdir(parents=True, exist_ok=True)
    report_json = scorecards_root / f"voice-sample-inventory-{today_slug()}.json"
    report_md = scorecards_root / f"voice-sample-inventory-{today_slug()}.md"
    state_json = STATE_ROOT / "latest-voice-quality-sample-inventory.json"
    state_md = STATE_ROOT / "latest-voice-quality-sample-inventory.md"

    blocker_notes = []
    if samples and not render_files:
        blocker_notes.append("No generated voice renders exist yet; sample capture is complete enough for first evaluation, but synthesis/evaluation has not been run.")
    if samples and not tool_checks["ffmpeg"]:
        blocker_notes.append("Local Apple audio tools cannot read the browser WebM files directly; install/configure a decoder or capture WAV via the Volt bridge before local model evaluation.")
    if not python_modules.get("TTS") and not python_modules.get("coqui_tts"):
        blocker_notes.append("No local voice-cloning TTS package is installed in the current Python environment.")

    report = {
        "generated_at": generated_at,
        "ok": bool(samples),
        "sample_count": len(samples),
        "missing_audio_count": sum(1 for sample in samples if not sample["has_audio"]),
        "expected_script_count": len(expected_scripts),
        "missing_script_ids": missing_script_ids,
        "render_count": len(render_files),
        "tool_checks": tool_checks,
        "python_modules": python_modules,
        "samples": samples,
        "blocker_notes": blocker_notes,
        "next_step": "Create a controlled local voice-render experiment from these consented samples, then score it before any demo or call usage.",
        "safety_boundary": "Internal consented voice-quality evaluation only. No live calls, outbound calls, public release, or undisclosed voice impersonation.",
    }

    lines = [
        "# JVT Voice Sample Inventory",
        "",
        f"Generated: {generated_at}",
        "",
        "Status: internal consented voice-quality evaluation only. Do not deploy to live calls from this report.",
        "",
        "## Summary",
        "",
        f"- Samples found: `{len(samples)}`",
        f"- Expected scripts: `{len(expected_scripts)}`",
        f"- Missing scripts: `{len(missing_script_ids)}`",
        f"- Generated renders found: `{len(render_files)}`",
        f"- Samples missing audio: `{report['missing_audio_count']}`",
        "",
        "## Tooling",
        "",
    ]
    for name, present in tool_checks.items():
        lines.append(f"- `{name}`: {'present' if present else 'missing'}")
    for name, present in python_modules.items():
        lines.append(f"- Python `{name}`: {'present' if present else 'missing'}")
    lines.extend(["", "## Blockers / Notes", ""])
    lines.extend([f"- {note}" for note in blocker_notes] or ["- None detected."])
    lines.extend(["", "## Samples", ""])
    for sample in samples:
        lines.append(f"- `{sample['script_id']}` - {sample['title']} - {sample['audio_bytes']} bytes - `{Path(sample['audio_path']).name if sample['audio_path'] else 'missing audio'}`")
    lines.extend([
        "",
        "## Next Step",
        "",
        report["next_step"],
        "",
        "Safety boundary: internal evaluation only; no live or outbound call use without explicit approval and disclosure.",
        "",
    ])

    write_json(report_json, report)
    write_json(state_json, report)
    report_md.write_text("\n".join(lines), encoding="utf-8")
    state_md.write_text("\n".join(lines), encoding="utf-8")
    return {
        "ok": report["ok"],
        "sample_count": len(samples),
        "render_count": len(render_files),
        "blocker_count": len(blocker_notes),
        "artifacts": [str(report_json), str(report_md), str(state_json), str(state_md)],
        "guardrail": report["safety_boundary"],
    }


def voice_readiness_check(_task: dict[str, Any]) -> dict[str, Any]:
    step = report_script("voice_readiness_check", "voice_readiness_check.py")
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(STATE_ROOT / "latest-voice-readiness.json"),
            str(STATE_ROOT / "latest-voice-readiness.md"),
        ],
        "guardrail": "Readiness reporting only. No live call enablement.",
    }


def local_audio_bridge_next_step(_task: dict[str, Any]) -> dict[str, Any]:
    health_step = run_command(
        "local_audio_bridge_health",
        [
            "python3",
            "-c",
            (
                "import json, urllib.request\n"
                "url='http://127.0.0.1:8761/health'\n"
                "try:\n"
                "    data=json.loads(urllib.request.urlopen(url, timeout=5).read().decode('utf-8'))\n"
                "except Exception as exc:\n"
                "    data={'ok': False, 'ready': False, 'error': str(exc)}\n"
                "print(json.dumps(data, sort_keys=True))\n"
            ),
        ],
        timeout=20,
    )
    readiness_step = report_script("voice_readiness_check", "voice_readiness_check.py")
    tool_steps = [
        run_command("ffmpeg_path", ["bash", "-lc", "command -v ffmpeg || true"], timeout=15),
        run_command("sox_path", ["bash", "-lc", "command -v sox || true"], timeout=15),
        run_command("mac_say_path", ["bash", "-lc", "command -v say || true"], timeout=15),
        run_command(
            "python_audio_module_probe",
            [
                "python3",
                "-c",
                (
                    "import importlib.util, json\n"
                    "mods=['numpy','soundfile','websockets','webrtcvad','faster_whisper']\n"
                    "print(json.dumps({name: bool(importlib.util.find_spec(name)) for name in mods}, sort_keys=True))\n"
                ),
            ],
            timeout=20,
        ),
    ]
    regression_step = run_command(
        "local_audio_bridge_media_stream_regression",
        ["python3", "products/Private-AI-Lab/apps/jvt-inbound-voice-agent/tools/test_local_audio_bridge_media_stream.py"],
        timeout=45,
    )
    post_regression_health_step = run_command(
        "local_audio_bridge_health_after_regression",
        [
            "python3",
            "-c",
            (
                "import json, urllib.request\n"
                "url='http://127.0.0.1:8761/health'\n"
                "try:\n"
                "    data=json.loads(urllib.request.urlopen(url, timeout=5).read().decode('utf-8'))\n"
                "except Exception as exc:\n"
                "    data={'ok': False, 'ready': False, 'error': str(exc)}\n"
                "print(json.dumps(data, sort_keys=True))\n"
            ),
        ],
        timeout=20,
    )

    bridge_health: dict[str, Any] = {}
    if health_step.get("stdout_tail"):
        raw_health = "\n".join(str(line) for line in health_step.get("stdout_tail") or [])
        try:
            bridge_health = json.loads(raw_health)
        except json.JSONDecodeError:
            bridge_health = {"ok": False, "ready": False, "parse_error": raw_health[-500:]}
    post_regression_bridge_health: dict[str, Any] = {}
    if post_regression_health_step.get("stdout_tail"):
        raw_health = "\n".join(str(line) for line in post_regression_health_step.get("stdout_tail") or [])
        try:
            post_regression_bridge_health = json.loads(raw_health)
        except json.JSONDecodeError:
            post_regression_bridge_health = {"ok": False, "ready": False, "parse_error": raw_health[-500:]}

    readiness = load_json(STATE_ROOT / "latest-voice-readiness.json", {})
    gates = readiness.get("gates") if isinstance(readiness, dict) and isinstance(readiness.get("gates"), dict) else {}
    next_steps = [
        {
            "step": "replace contract-only bridge with real audio turn pipeline",
            "detail": "Decode Twilio PCMU frames, buffer speech turns with VAD, transcribe locally, route text through the model router, synthesize reply audio, and encode outbound PCMU frames.",
            "owner": "voice-bridge-agent",
        },
        {
            "step": "select local STT backend",
            "detail": "Prefer the lowest-latency local backend that can run on the M4 without cloud keys. Validate with recorded dental/JVT prompt samples before live routing.",
            "owner": "voice-bridge-agent",
        },
        {
            "step": "select low-latency TTS path",
            "detail": "Use the current voice samples for style direction, but do not deploy cloned voice audio until latency, consent, and disclosure wording are approved.",
            "owner": "voice-quality-agent",
        },
        {
            "step": "add synthetic media-stream regression",
            "detail": "Feed sample inbound frames through the websocket bridge and require health to report ready only after STT, model, TTS, and return-audio checks pass.",
            "owner": "qa-agent",
        },
    ]
    report = {
        "generated_at": utc_now(),
        "ok": bool(readiness_step.get("ok")) and bool(regression_step.get("ok")),
        "bridge_health": bridge_health,
        "post_regression_bridge_health": post_regression_bridge_health,
        "voice_readiness": {
            "demo_ready": readiness.get("demo_ready") if isinstance(readiness, dict) else None,
            "live_ready": readiness.get("live_ready") if isinstance(readiness, dict) else None,
            "mode": readiness.get("mode") if isinstance(readiness, dict) else "",
            "response_engine": readiness.get("response_engine") if isinstance(readiness, dict) else "",
            "gates": gates,
            "blockers": readiness.get("blockers") if isinstance(readiness, dict) else [],
        },
        "next_steps": next_steps,
        "health_gate": {
            "current": bool(gates.get("local_audio_bridge_ready")),
            "required_before_live": [
                "bridge health reports ready=true",
                "synthetic media-stream regression passes",
                "provider routing stays dry-run until explicitly approved",
            ],
            "synthetic_regression_ok": bool(regression_step.get("ok")),
        },
        "guardrail": "Internal bridge-readiness work only. No provider credentials, live routing, or outbound calls are enabled.",
        "steps": [health_step, readiness_step, *tool_steps, regression_step, post_regression_health_step],
    }

    state_json = STATE_ROOT / "latest-local-audio-bridge-next-step.json"
    state_md = STATE_ROOT / "latest-local-audio-bridge-next-step.md"
    strategy_md = REPO_ROOT / "strategy" / "voice" / f"local-audio-bridge-next-step-{today_slug()}.md"
    lines = [
        "# Local Audio Bridge Next Step",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Bridge health: `{bridge_health.get('status') or 'unknown'}`",
        f"- Bridge ready: `{bridge_health.get('ready')}`",
        f"- Voice live-ready: `{report['voice_readiness'].get('live_ready')}`",
        f"- Local bridge gate: `{gates.get('local_audio_bridge_ready')}`",
        "",
        "## Required Build Steps",
        "",
    ]
    for item in next_steps:
        lines.extend([
            f"- `{item['owner']}`: {item['step']}. {item['detail']}",
        ])
    lines.extend([
        "",
        "## Guardrail",
        "",
        report["guardrail"],
        "",
        "Do not mark the bridge ready until health reports `ready=true` and the synthetic media-stream regression proves local STT, model response, TTS, and return audio.",
        "",
    ])
    write_json(state_json, report)
    state_md.write_text("\n".join(lines), encoding="utf-8")
    strategy_md.parent.mkdir(parents=True, exist_ok=True)
    strategy_md.write_text("\n".join(lines), encoding="utf-8")
    return {
        "ok": report["ok"],
        "steps": [health_step, readiness_step, *tool_steps, regression_step, post_regression_health_step],
        "artifacts": [str(state_json), str(state_md), str(strategy_md)],
        "bridge_ready": bool(gates.get("local_audio_bridge_ready")),
        "guardrail": report["guardrail"],
    }


def vertical_lead_research_refresh(task: dict[str, Any]) -> dict[str, Any]:
    raw_lanes = task.get("lanes") or [
        "dental_voice",
        "it_ballot",
        "local_receptionist",
        "insurance",
        "property",
        "construction",
    ]
    if isinstance(raw_lanes, str):
        lanes = [part.strip() for part in raw_lanes.split(",") if part.strip()]
    else:
        lanes = [str(part).strip() for part in raw_lanes if str(part).strip()]
    if not lanes:
        lanes = ["dental_voice", "it_ballot", "local_receptionist", "insurance"]
    queries_per_run = int(task.get("queries_per_run") or 4)
    results_per_query = int(task.get("results_per_query") or 6)
    max_new_leads = int(task.get("max_new_leads") or 5)
    draft_limit = int(task.get("draft_limit") or 3)
    step = run_command(
        "vertical_lead_research_refresh",
        [
            "python3",
            "lead-pipeline/tools/auto_research.py",
            "--queries-per-run",
            str(max(1, queries_per_run)),
            "--results-per-query",
            str(max(1, results_per_query)),
            "--max-new-leads",
            str(max(0, max_new_leads)),
            "--draft-limit",
            str(max(0, draft_limit)),
            "--lanes",
            ",".join(lanes),
            "--model-screen",
            "optional",
        ],
        timeout=900,
    )
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "lanes": lanes,
        "artifacts": [
            str(REPO_ROOT / "lead-pipeline" / "state"),
            str(REPO_ROOT / "outreach" / "queue" / "draft"),
            str(REPO_ROOT / "outreach" / "queue" / "review"),
        ],
        "guardrail": "Research and packet staging only. Recipient quality gates still control approval and delivery.",
    }


def opportunity_hit_sync(_task: dict[str, Any]) -> dict[str, Any]:
    steps = [
        run_command("operator_notifier_state", ["python3", "ops/agent-control/operator_notifier.py"], timeout=90),
        run_command("jvt_ops_db_sync", ["python3", "ops/agent-control/jvt_ops_db.py", "sync"], timeout=120),
        report_script("opportunity_manager", "opportunity_manager.py"),
        run_command("agent_interop_check", ["python3", "ops/agent-control/agent_interop_check.py"], timeout=90),
    ]
    return {
        "ok": all(step["ok"] for step in steps),
        "steps": steps,
        "artifacts": [
            str(STATE_ROOT / "operator-notifier" / "latest-alerts.json"),
            str(STATE_ROOT / "operator-notifier" / "latest-alerts.md"),
            str(STATE_ROOT / "latest-jvt-ops-db.json"),
            str(STATE_ROOT / "latest-opportunity-manager.json"),
            str(STATE_ROOT / "latest-opportunity-manager.md"),
            str(STATE_ROOT / "latest-agent-interop.md"),
        ],
        "guardrail": "Internal hit tracking and operator alert state only. No outbound prospect action is initiated here.",
    }


def service_pilot_package_refresh(task: dict[str, Any]) -> dict[str, Any]:
    package_handlers = [
        dental_voice_intake_pilot_brief,
        it_ballot_workflow_pilot_brief,
        insurance_coi_proof_asset,
        meeting_to_action_content_packet,
        content_backlog_from_assets,
        offer_segment_summary,
        venture_scout_index,
    ]
    items: list[dict[str, Any]] = []
    artifacts: list[str] = []
    for handler in package_handlers:
        result = handler(task)
        items.append({"handler": handler.__name__, **result})
        artifacts.extend(str(path) for path in result.get("artifacts", []))
    return {
        "ok": all(item.get("ok") for item in items),
        "items": items,
        "artifacts": sorted(set(artifacts)),
        "guardrail": "Internal proof and pilot packaging only. No commitments, platform publication, or live provider usage.",
    }


def opportunity_manager_refresh(_task: dict[str, Any]) -> dict[str, Any]:
    step = report_script("opportunity_manager", "opportunity_manager.py")
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(STATE_ROOT / "latest-opportunity-manager.json"),
            str(STATE_ROOT / "latest-opportunity-manager.md"),
        ],
        "guardrail": "Opportunity state reporting only. No external replies or follow-ups are sent.",
    }


def source_hygiene_report(_task: dict[str, Any]) -> dict[str, Any]:
    step = report_script("source_hygiene_report", "source_hygiene_report.py")
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(STATE_ROOT / "latest-source-hygiene.json"),
            str(STATE_ROOT / "latest-source-hygiene.md"),
        ],
        "guardrail": "Source inspection only. No git reset, commit, push, or deletion.",
    }


def system_resource_report(_task: dict[str, Any]) -> dict[str, Any]:
    step = report_script("system_resource_report", "system_resource_report.py")
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(STATE_ROOT / "latest-system-resources.json"),
            str(STATE_ROOT / "latest-system-resources.md"),
        ],
        "guardrail": "System reporting only. No service changes or reboot.",
    }


def business_readiness_sweep(_task: dict[str, Any]) -> dict[str, Any]:
    steps = [
        report_script("opportunity_manager", "opportunity_manager.py"),
        report_script("voice_readiness_check", "voice_readiness_check.py"),
        report_script("paper_trader_health", "paper_trader_health.py"),
        report_script("source_hygiene_report", "source_hygiene_report.py"),
        report_script("system_resource_report", "system_resource_report.py"),
        run_command("agent_interop_check", ["python3", "ops/agent-control/agent_interop_check.py"], timeout=90),
    ]
    return {
        "ok": all(step["ok"] for step in steps),
        "steps": steps,
        "artifacts": [
            str(STATE_ROOT / "latest-opportunity-manager.json"),
            str(STATE_ROOT / "latest-voice-readiness.json"),
            str(STATE_ROOT / "latest-paper-trader-health.json"),
            str(STATE_ROOT / "latest-source-hygiene.json"),
            str(STATE_ROOT / "latest-system-resources.json"),
            str(STATE_ROOT / "latest-agent-interop.json"),
        ],
        "guardrail": "Readiness sweep only. It reports what needs action but does not perform external outreach delivery, spending, market orders, crypto network participation, public posting, commits, or external commitments.",
    }


def work_item_materializer(_task: dict[str, Any]) -> dict[str, Any]:
    step = report_script("work_item_materializer", "work_item_materializer.py")
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(STATE_ROOT / "latest-work-item-materializer.json"),
            str(STATE_ROOT / "latest-work-item-materializer.md"),
        ],
        "guardrail": "Materializes orchestrator work items into internal allowlisted tasks/specs only. No external outreach delivery, spending, market orders, crypto custody/network participation, public posting, provider enablement, or commitments.",
    }


def egg_task_generator(_task: dict[str, Any]) -> dict[str, Any]:
    step = report_script("egg_agent", "egg_agent.py", timeout=120)
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(STATE_ROOT / "latest-egg-agent.json"),
            str(STATE_ROOT / "latest-egg-agent.md"),
        ],
        "guardrail": "Generates internal allowlisted tasks from company state and design ethos only. No external outreach delivery, spending, market orders, crypto custody/network participation, public posting, provider enablement, or commitments.",
    }


def agent_repair_escalation(task: dict[str, Any]) -> dict[str, Any]:
    agent = str(task.get("agent") or "egg")
    step = run_command(
        "agent_repair_escalator",
        ["python3", "ops/agent-control/agent_repair_escalator.py", "--agent", agent, "--force-epic"],
        timeout=120,
    )
    return {
        "ok": bool(step["ok"]),
        "steps": [step],
        "artifacts": [
            str(STATE_ROOT / "latest-agent-repair.json"),
            str(STATE_ROOT / "latest-agent-repair.md"),
        ],
        "guardrail": "Internal repair triage only. External operations and account/provider actions remain out of scope.",
    }


HANDLERS = {
    "refresh_growth_state": refresh_growth_state,
    "codex_cli_version_snapshot": codex_cli_version_snapshot,
    "model_router_status": model_router_status,
    "codex_escalation_status": codex_escalation_status,
    "jvt_ops_db_sync": jvt_ops_db_sync,
    "opportunity_hit_sync": opportunity_hit_sync,
    "opportunity_manager_refresh": opportunity_manager_refresh,
    "vertical_lead_research_refresh": vertical_lead_research_refresh,
    "service_pilot_package_refresh": service_pilot_package_refresh,
    "voice_quality_sample_inventory": voice_quality_sample_inventory,
    "voice_readiness_check": voice_readiness_check,
    "local_audio_bridge_next_step": local_audio_bridge_next_step,
    "paper_trader_health": paper_trader_health,
    "source_hygiene_report": source_hygiene_report,
    "system_resource_report": system_resource_report,
    "business_readiness_sweep": business_readiness_sweep,
    "work_item_materializer": work_item_materializer,
    "egg_task_generator": egg_task_generator,
    "agent_repair_escalation": agent_repair_escalation,
    "inbox_triage_brief": inbox_triage_brief,
    "outreach_review_queue_brief": outreach_review_queue_brief,
    "followup_review_brief": followup_review_brief,
    "content_backlog_from_assets": content_backlog_from_assets,
    "insurance_coi_proof_asset": insurance_coi_proof_asset,
    "it_ballot_workflow_pilot_brief": it_ballot_workflow_pilot_brief,
    "dental_voice_intake_pilot_brief": dental_voice_intake_pilot_brief,
    "meeting_to_action_content_packet": meeting_to_action_content_packet,
    "offer_segment_summary": offer_segment_summary,
    "venture_scout_index": venture_scout_index,
    "paper_trader_refresh": paper_trader_refresh,
    "priority_packet_review_queue": priority_packet_review_queue,
    "ten_k_execution_digest": ten_k_execution_digest,
}


def move_task(path: Path, target_dir: str, result: dict[str, Any]) -> Path:
    target = TASK_ROOT / target_dir / path.name
    payload = load_json(path, {})
    payload["runner_result"] = result
    payload["runner_updated_at"] = utc_now()
    write_json(path, payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(f"{target.stem}-{int(time.time())}{target.suffix}")
    shutil.move(str(path), str(target))
    return target


def acquire_lock() -> int:
    ensure_dirs()
    try:
        return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - LOCK_PATH.stat().st_mtime if LOCK_PATH.exists() else 0
        if age > 1800:
            LOCK_PATH.unlink(missing_ok=True)
            return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        raise SystemExit("Local task runner is already running.")


def run_pending(max_tasks: int) -> dict[str, Any]:
    ensure_dirs()
    assignment_policy = load_assignment_policy()
    pending = sorted((TASK_ROOT / "pending").glob("*.json"))[:max_tasks]
    processed: list[dict[str, Any]] = []
    for path in pending:
        task = load_json(path, {})
        task_type = str(task.get("type") or "")
        assignment = task_assignment(task, assignment_policy)
        base = {"task_file": str(path), "task_id": task.get("id") or path.stem, "type": task_type, "assignment": assignment}
        reason = hold_reason(task)
        if reason:
            held_path = move_task(path, "held", {**base, "ok": False, "held": True, "reason": reason})
            processed.append({**base, "status": "held", "path": str(held_path), "reason": reason})
            continue
        handler = HANDLERS.get(task_type)
        if not handler:
            held_path = move_task(path, "held", {**base, "ok": False, "held": True, "reason": "Unsupported task type."})
            processed.append({**base, "status": "held", "path": str(held_path), "reason": "Unsupported task type."})
            continue
        running_path = TASK_ROOT / "running" / path.name
        if running_path.exists():
            running_path = running_path.with_name(f"{running_path.stem}-{int(time.time())}{running_path.suffix}")
        shutil.move(str(path), str(running_path))
        try:
            result = handler(task)
            self_review = self_review_task_result(task, result, assignment)
            result = {**result, "assignment": assignment, "self_review": self_review}
            target_dir = "completed" if result.get("ok") and self_review.get("ok") else "failed"
            final_path = move_task(running_path, target_dir, {**base, **result})
            processed.append({
                **base,
                "status": target_dir,
                "path": str(final_path),
                "ok": bool(result.get("ok")) and bool(self_review.get("ok")),
                "self_review_ok": bool(self_review.get("ok")),
                "self_review_findings": int(self_review.get("finding_count") or 0),
            })
        except Exception as exc:
            final_path = move_task(running_path, "failed", {**base, "ok": False, "error": repr(exc)})
            processed.append({**base, "status": "failed", "path": str(final_path), "error": repr(exc)})
    return {
        "generated_at": utc_now(),
        "ok": all(item.get("status") == "completed" for item in processed) if processed else True,
        "processed_count": len(processed),
        "processed": processed,
        "pending_remaining": len(list((TASK_ROOT / "pending").glob("*.json"))),
        "supported_task_types": sorted(HANDLERS),
        "assignment_policy_path": str(ASSIGNMENT_POLICY_PATH),
        "assignment_policy_version": assignment_policy.get("version"),
        "hierarchy_levels": assignment_policy.get("hierarchy"),
        "safety_boundary": "Allowlisted internal tasks only. No arbitrary shell, external outreach delivery, spending, account changes, market orders, crypto custody/network participation, public posting, or external commitments.",
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# JVT Local Task Runner",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Overall: `{'ok' if report.get('ok') else 'attention'}`",
        f"- Processed: `{report.get('processed_count')}`",
        f"- Pending remaining: `{report.get('pending_remaining')}`",
        f"- Safety: {report.get('safety_boundary')}",
        "",
        "## Processed Tasks",
        "",
    ]
    for item in report.get("processed", []):
        assignment = item.get("assignment") if isinstance(item.get("assignment"), dict) else {}
        lines.append(
            f"- `{item.get('status')}` {item.get('task_id')} ({item.get('type')}) "
            f"level=`{assignment.get('level')}` model=`{assignment.get('model_tier')}` "
            f"self-review=`{item.get('self_review_ok')}` findings=`{item.get('self_review_findings', 0)}`"
        )
    if not report.get("processed"):
        lines.append("- No pending tasks were available.")
    lines.extend(["", "## Assignment Policy", ""])
    lines.append(f"- Policy: `{report.get('assignment_policy_path')}`")
    lines.append(f"- Version: `{report.get('assignment_policy_version')}`")
    lines.extend(["", "## Supported Task Types", ""])
    for task_type in report.get("supported_task_types", []):
        lines.append(f"- `{task_type}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run allowlisted local JVT tasks.")
    parser.add_argument("--max-tasks", type=int, default=3)
    args = parser.parse_args()

    lock_fd = acquire_lock()
    try:
        os.write(lock_fd, str(os.getpid()).encode("utf-8"))
        report = run_pending(max(1, args.max_tasks))
        json_path = STATE_ROOT / "latest-local-task-runner.json"
        markdown_path = STATE_ROOT / "latest-local-task-runner.md"
        write_json(json_path, report)
        write_markdown(report, markdown_path)
        print(json.dumps({"ok": report["ok"], "processed_count": report["processed_count"], "json_path": str(json_path)}))
        if not report["ok"]:
            raise SystemExit(1)
    finally:
        os.close(lock_fd)
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"ok": False, "error": f"Timed out: {exc}"}), file=sys.stderr)
        raise
