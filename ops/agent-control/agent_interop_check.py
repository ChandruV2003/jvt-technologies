#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
AGENT_ROOT = CONTROL_ROOT / "agents"
STATE_ROOT = CONTROL_ROOT / "state"
LEAD_DB = REPO_ROOT / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
OUTREACH_QUEUE = REPO_ROOT / "outreach" / "queue"
INBOX_ROOT = REPO_ROOT / "outreach" / "inbox"
FOLLOWUP_REPORT_DIR = REPO_ROOT / "outreach" / "schedules" / "followups"
COPYWRITER_REPORT = REPO_ROOT / "outreach" / "schedules" / "copywriter" / "latest-agentic-rewrite.json"
WATCHDOG_STATE = REPO_ROOT / "ops" / "watchdog" / "state" / "latest-watchdog.json"
ORCHESTRATOR_STATE = CONTROL_ROOT / "state" / "latest-orchestrator.json"
GROWTH_CHECKIN_STATE = CONTROL_ROOT / "state" / "latest-growth-ops-checkin.json"
VENTURE_PIPELINE_STATE = CONTROL_ROOT / "state" / "latest-venture-pipeline.json"
EOM_STATE = CONTROL_ROOT / "state" / "latest-eom-brief.json"
LOCAL_TASK_RUNNER_STATE = CONTROL_ROOT / "state" / "latest-local-task-runner.json"
EPIC_AGENT_STATE = CONTROL_ROOT / "state" / "latest-epic-agent.json"
MODEL_ROUTER_STATE = CONTROL_ROOT / "state" / "latest-model-router.json"
CODEX_ESCALATION_STATE = CONTROL_ROOT / "state" / "latest-codex-escalation.json"
OPS_DB_STATE = CONTROL_ROOT / "state" / "latest-jvt-ops-db.json"
EPIC_ROOT = CONTROL_ROOT / "epics"
VOICE_APP_ROOT = REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "jvt-inbound-voice-agent"
CLIENT_REGISTRY = Path("/Users/c.s.d.v.r.s./Documents/JVT-Technologies/00-admin/client-registry.csv")

REQUIRED_AGENTS = {
    "billing-admin",
    "client-ops",
    "delivery",
    "egg",
    "epic-agent",
    "executive-ops-manager",
    "intake",
    "lead-research",
    "local-task-runner",
    "orchestrator",
    "outreach",
    "qa-review",
    "solution-planning",
    "voice-receptionist",
}
REQUIRED_AGENT_FIELDS = ("slug", "name", "role", "mode", "status", "approval_boundary", "owns", "data_sources")
LAUNCH_LABELS = {
    "control-panel": "com.jvt.control-panel",
    "watchdog": "com.jvt.watchdog",
    "orchestrator": "com.jvt.orchestrator",
    "growth-ops-checkin": "com.jvt.growth-ops-checkin",
    "ai-director": "com.jvt.ai-director",
    "egg": "com.jvt.egg-agent",
    "local-task-runner": "com.jvt.local-task-runner",
    "epic-agent": "com.jvt.epic-agent",
    "lead-research": "com.jvt.lead-research",
    "daily-wave-prep": "com.jvt.daily-wave-prep",
    "mailbox-listener": "com.jvt.mailbox-listener",
    "agentic-copywriter": "com.jvt.agentic-copywriter",
    "model-router": "com.jvt.model-router",
    "voice-receptionist": "com.jvt.inbound-voice-agent",
    "private-doc-intel-demo": "com.jvt.private-doc-intel-demo",
}
ENDPOINTS = {
    "control-health": "http://127.0.0.1:8042/health",
    "control-agents": "http://127.0.0.1:8042/api/agents",
    "voice-status": "http://127.0.0.1:8066/health",
    "model-router": "http://127.0.0.1:8760/health",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def count_files(path: Path, pattern: str = "*.json") -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob(pattern) if item.is_file())


def launchctl_snapshot() -> dict[str, dict[str, Any]]:
    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
    by_label: dict[str, dict[str, Any]] = {}
    if result.returncode != 0:
        return {
            label: {
                "label": launch_label,
                "registered": False,
                "running": False,
                "ok": False,
                "last_exit": None,
                "error": result.stderr.strip() or "launchctl list failed",
            }
            for label, launch_label in LAUNCH_LABELS.items()
        }

    raw: dict[str, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        pid_raw, exit_raw, label = parts[0], parts[1], parts[2]
        raw[label] = {
            "pid": None if pid_raw == "-" else pid_raw,
            "last_exit": None if exit_raw == "-" else exit_raw,
            "running": pid_raw != "-",
        }

    for key, launch_label in LAUNCH_LABELS.items():
        item = raw.get(launch_label, {})
        last_exit = item.get("last_exit")
        clean_exit = str(last_exit) in {"0", "None"} or last_exit is None
        by_label[key] = {
            "label": launch_label,
            "registered": bool(item),
            "running": bool(item.get("running")),
            "last_exit": last_exit,
            "ok": bool(item) and (bool(item.get("running")) or clean_exit),
        }
    return by_label


def endpoint_snapshot(timeout_seconds: float = 3.0) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for name, url in ENDPOINTS.items():
        timeout = 10.0 if name == "control-agents" else timeout_seconds
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                status = int(response.status)
                body = response.read(256)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            items[name] = {"url": url, "ok": False, "status": None, "error": str(exc)}
            continue
        items[name] = {
            "url": url,
            "ok": 200 <= status < 300,
            "status": status,
            "sample_bytes": len(body),
        }
    return items


def manifest_snapshot() -> dict[str, Any]:
    manifests: list[dict[str, Any]] = []
    present_slugs: set[str] = set()
    invalid: list[dict[str, Any]] = []
    if AGENT_ROOT.exists():
        for path in sorted(AGENT_ROOT.glob("*.json")):
            payload = load_json(path)
            slug = str(payload.get("slug") or path.stem)
            present_slugs.add(slug)
            missing = [field for field in REQUIRED_AGENT_FIELDS if not payload.get(field)]
            item = {
                "slug": slug,
                "name": payload.get("name") or slug,
                "mode": payload.get("mode") or "unknown",
                "status": payload.get("status") or "unknown",
                "path": str(path),
                "missing_fields": missing,
            }
            manifests.append(item)
            if missing:
                invalid.append(item)
    missing_required = sorted(REQUIRED_AGENTS - present_slugs)
    return {
        "ok": not invalid and not missing_required,
        "count": len(manifests),
        "active_declared": sum(1 for item in manifests if item.get("status") == "active"),
        "review_driven": sum(1 for item in manifests if item.get("mode") == "review-driven"),
        "autonomous": sum(1 for item in manifests if item.get("mode") == "autonomous"),
        "missing_required": missing_required,
        "invalid": invalid,
        "items": manifests,
    }


def handoff(name: str, source: str, target: str, ok: bool, evidence: str, next_step: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "source": source,
        "target": target,
        "status": "ok" if ok else "attention",
        "ok": ok,
        "evidence": evidence,
        "next_step": next_step,
    }


def handoff_snapshot(launchd: dict[str, dict[str, Any]], endpoints: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    queue_dirs_ok = all((OUTREACH_QUEUE / label).exists() for label in ("draft", "review", "approved", "sent", "replied"))
    review_count = count_files(OUTREACH_QUEUE / "review")
    approved_count = count_files(OUTREACH_QUEUE / "approved")
    inbox_new_count = count_files(INBOX_ROOT / "new")
    voice_data_ok = (VOICE_APP_ROOT / "data").exists()
    watchdog_payload = load_json(WATCHDOG_STATE)
    orchestrator_payload = load_json(ORCHESTRATOR_STATE)
    growth_checkin_payload = load_json(GROWTH_CHECKIN_STATE)
    venture_pipeline_payload = load_json(VENTURE_PIPELINE_STATE)
    eom_payload = load_json(EOM_STATE)
    local_task_runner_payload = load_json(LOCAL_TASK_RUNNER_STATE)
    epic_agent_payload = load_json(EPIC_AGENT_STATE)
    model_router_payload = load_json(MODEL_ROUTER_STATE)
    codex_payload = load_json(CODEX_ESCALATION_STATE)
    ops_db_payload = load_json(OPS_DB_STATE)
    copywriter_payload = load_json(COPYWRITER_REPORT)
    epic_queue_ok = all((EPIC_ROOT / folder).exists() for folder in ("queued", "running", "done", "blocked", "held", "architect-inbox"))

    return [
        handoff(
            "Model router to local inference backends",
            "model-router",
            "all-model-backed-agents",
            MODEL_ROUTER_STATE.exists() and bool(model_router_payload.get("ok")) and bool(endpoints.get("model-router", {}).get("ok")),
            f"router_state={MODEL_ROUTER_STATE.exists()}, router_ok={model_router_payload.get('ok')}, endpoint={endpoints.get('model-router', {}).get('ok')}, backends={model_router_payload.get('available_backends')}",
            "Route model-backed agent work through the router instead of direct random model ports.",
        ),
        handoff(
            "Codex escalation wrapper",
            "codex-escalation-runner",
            "solution-planning",
            CODEX_ESCALATION_STATE.exists() and bool(codex_payload.get("enabled")) and bool(codex_payload.get("codex_cli")),
            f"codex_state={CODEX_ESCALATION_STATE.exists()}, enabled={codex_payload.get('enabled')}, auth={codex_payload.get('auth_present')}, usage={codex_payload.get('usage')}",
            "Use Codex/GPT only through capped, audited escalation packets; no autonomous paid execution by default.",
        ),
        handoff(
            "Ops database to company memory",
            "jvt-ops-db",
            "all-agents",
            OPS_DB_STATE.exists() and bool(ops_db_payload.get("ok")),
            f"ops_db_state={OPS_DB_STATE.exists()}, tables={(ops_db_payload.get('table_counts') or {})}",
            "Use the ops DB as the durable source of truth for leads, service fit, interactions, queues, and backend status.",
        ),
        handoff(
            "Growth check-in to orchestrator",
            "growth-ops-checkin",
            "orchestrator",
            GROWTH_CHECKIN_STATE.exists() and bool(launchd.get("growth-ops-checkin", {}).get("ok")),
            f"checkin_state={GROWTH_CHECKIN_STATE.exists()}, checkin_launch={launchd.get('growth-ops-checkin', {}).get('ok')}, safe_actions={len(growth_checkin_payload.get('safe_actions') or [])}",
            "Keep the recurring check-in active so health, follow-up candidates, and orchestration state stay fresh.",
        ),
        handoff(
            "Orchestrator to agent lanes",
            "orchestrator",
            "all-agents",
            ORCHESTRATOR_STATE.exists() and bool(launchd.get("orchestrator", {}).get("ok")),
            f"orchestrator_state={ORCHESTRATOR_STATE.exists()}, orchestrator_launch={launchd.get('orchestrator', {}).get('ok')}, work_items={len(orchestrator_payload.get('work_items') or [])}",
            "Keep the Growth OS state fresh so each lane has ranked work items and clear approval boundaries.",
        ),
        handoff(
            "Venture pipeline to EOM",
            "venture-pipeline",
            "executive-ops-manager",
            VENTURE_PIPELINE_STATE.exists() and EOM_STATE.exists(),
            f"venture_state={VENTURE_PIPELINE_STATE.exists()}, eom_state={EOM_STATE.exists()}, venture_items={len(venture_pipeline_payload.get('work_items') or [])}, eom_mode={(eom_payload.get('focus') or {}).get('mode')}",
            "Keep the EOM brief fresh so cash-flow lanes produce one clear next action instead of an unprioritized idea pile.",
        ),
        handoff(
            "EOM to local task runner",
            "executive-ops-manager",
            "local-task-runner",
            EOM_STATE.exists() and LOCAL_TASK_RUNNER_STATE.exists() and bool(launchd.get("local-task-runner", {}).get("ok")),
            f"eom_state={EOM_STATE.exists()}, task_runner_state={LOCAL_TASK_RUNNER_STATE.exists()}, task_runner_launch={launchd.get('local-task-runner', {}).get('ok')}, processed={local_task_runner_payload.get('processed_count')}",
            "Use the local task runner for allowlisted internal prep work; hold anything that needs approval.",
        ),
        handoff(
            "Solution architect to epic agent",
            "solution-planning",
            "epic-agent",
            epic_queue_ok and EPIC_AGENT_STATE.exists() and bool(launchd.get("epic-agent", {}).get("ok")),
            f"epic_queue={epic_queue_ok}, epic_state={EPIC_AGENT_STATE.exists()}, epic_launch={launchd.get('epic-agent', {}).get('ok')}, processed={epic_agent_payload.get('processed_count')}",
            "Use the epic queue for large durable stories; blocked or completed work returns through architect-inbox.",
        ),
        handoff(
            "Research to outreach drafting",
            "lead-research",
            "outreach",
            LEAD_DB.exists() and queue_dirs_ok and bool(launchd.get("lead-research", {}).get("ok")),
            f"lead_db={LEAD_DB.exists()}, queue_dirs={queue_dirs_ok}, lead_research_launch={launchd.get('lead-research', {}).get('ok')}",
            "Keep lead research running; packet generation remains human-reviewed before send.",
        ),
        handoff(
            "Outreach to QA review",
            "outreach",
            "qa-review",
            queue_dirs_ok and (REPO_ROOT / "outreach" / "tools" / "quality_gate_approved.py").exists(),
            f"review={review_count}, approved={approved_count}, quality_gate={(REPO_ROOT / 'outreach' / 'tools' / 'quality_gate_approved.py').exists()}",
            "Review queue quality still depends on conservative recipient checks before approval.",
        ),
        handoff(
            "Agentic copywriter to QA review",
            "agentic-copywriter",
            "qa-review",
            COPYWRITER_REPORT.exists() and bool(launchd.get("agentic-copywriter", {}).get("ok")),
            f"copywriter_report={COPYWRITER_REPORT.exists()}, copywriter_launch={launchd.get('agentic-copywriter', {}).get('ok')}, rewritten={copywriter_payload.get('rewritten_count')}, checked={copywriter_payload.get('result_count')}",
            "The copywriter may rewrite staged unsent packets, but QA/quality-gate still owns approval and send eligibility.",
        ),
        handoff(
            "No-reply follow-up loop",
            "mailbox-listener",
            "outreach",
            INBOX_ROOT.exists() and FOLLOWUP_REPORT_DIR.exists() and bool(launchd.get("mailbox-listener", {}).get("registered")),
            f"inbox_new={inbox_new_count}, followup_reports={FOLLOWUP_REPORT_DIR.exists()}, mailbox_registered={launchd.get('mailbox-listener', {}).get('registered')}",
            "Triage new inbox items before widening send volume.",
        ),
        handoff(
            "Voice intake to requirements",
            "voice-receptionist",
            "intake",
            VOICE_APP_ROOT.exists() and voice_data_ok and bool(launchd.get("voice-receptionist", {}).get("registered")),
            f"voice_app={VOICE_APP_ROOT.exists()}, data={voice_data_ok}, voice_registered={launchd.get('voice-receptionist', {}).get('registered')}",
            "Live calls still need webhook/provider/OpenAI configuration; dry-run intake can continue safely.",
        ),
        handoff(
            "Watchdog to control panel",
            "watchdog",
            "orchestrator",
            WATCHDOG_STATE.exists() and bool(endpoints.get("control-health", {}).get("ok")),
            f"watchdog_state={WATCHDOG_STATE.exists()}, control_health={endpoints.get('control-health', {}).get('ok')}, findings={len(watchdog_payload.get('findings') or [])}",
            "Resolve watchdog findings before increasing automation volume.",
        ),
        handoff(
            "Client ops to delivery",
            "client-ops",
            "delivery",
            CLIENT_REGISTRY.exists() or CLIENT_REGISTRY.parent.exists(),
            f"client_registry={CLIENT_REGISTRY.exists()}, registry_parent={CLIENT_REGISTRY.parent.exists()}",
            "First paid client should go through registry, workspace setup, then delivery scope review.",
        ),
    ]


def build_report() -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    launchd = launchctl_snapshot()
    endpoints = endpoint_snapshot()
    manifests = manifest_snapshot()
    handoffs = handoff_snapshot(launchd, endpoints)
    findings: list[dict[str, str]] = []

    if not manifests["ok"]:
        findings.append({"level": "warning", "message": "One or more agent manifests are missing required fields."})
    for key, item in launchd.items():
        if not item.get("ok"):
            findings.append({
                "level": "warning",
                "message": f"{item.get('label')} is not cleanly registered/running.",
            })
    for key, item in endpoints.items():
        if key == "voice-status" and not item.get("ok"):
            findings.append({
                "level": "notice",
                "message": "Voice HTTP health is not reachable; this is expected until live/dry-run service is active.",
            })
            continue
        if not item.get("ok"):
            findings.append({"level": "warning", "message": f"{key} endpoint is not reachable."})
    for item in handoffs:
        if not item.get("ok"):
            findings.append({"level": "warning", "message": f"Handoff needs attention: {item['name']}."})

    blocking_findings = [item for item in findings if item.get("level") != "notice"]

    return {
        "generated_at": generated_at,
        "ok": not blocking_findings,
        "finding_count": len(findings),
        "blocking_finding_count": len(blocking_findings),
        "findings": findings,
        "manifest_summary": manifests,
        "launchd": launchd,
        "endpoints": endpoints,
        "handoffs": handoffs,
        "summary": {
            "registered_launch_agents": sum(1 for item in launchd.values() if item.get("registered")),
            "clean_launch_agents": sum(1 for item in launchd.values() if item.get("ok")),
            "agent_manifests": manifests["count"],
            "handoffs_ok": sum(1 for item in handoffs if item.get("ok")),
            "handoffs_total": len(handoffs),
        },
        "safety_boundary": "No sends, payments, live trades, or external commitments are performed by this check.",
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# JVT Agent Interop Check",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Overall: `{'ok' if report.get('ok') else 'attention'}`",
        f"- Safety: {report['safety_boundary']}",
        "",
        "## Handoffs",
        "",
    ]
    for item in report.get("handoffs", []):
        lines.append(
            f"- `{item['status']}` {item['source']} -> {item['target']}: {item['name']} ({item['evidence']})"
        )
    lines.extend(["", "## Findings", ""])
    findings = report.get("findings", [])
    if findings:
        for finding in findings:
            lines.append(f"- `{finding['level']}` {finding['message']}")
    else:
        lines.append("- No active findings.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate JVT agent registry, launch agents, endpoints, and handoff readiness.")
    parser.add_argument("--state-dir", type=Path, default=STATE_ROOT)
    args = parser.parse_args()

    report = build_report()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.state_dir / "latest-agent-interop.json"
    markdown_path = args.state_dir / "latest-agent-interop.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown_path)
    print(json.dumps({
        "ok": report["ok"],
        "finding_count": report["finding_count"],
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }))


if __name__ == "__main__":
    main()
