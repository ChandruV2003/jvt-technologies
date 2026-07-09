#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_ROOT = REPO_ROOT / "ops" / "agent-control" / "state"
TASK_ROOT = REPO_ROOT / "ops" / "agent-control" / "tasks"
QUEUE_ROOT = REPO_ROOT / "outreach" / "queue"
SCHEDULE_ROOT = REPO_ROOT / "outreach" / "schedules"
FOLLOWUP_ROOT = SCHEDULE_ROOT / "followups"
LOCK_PATH = STATE_ROOT / "growth-ops-checkin.lock"

AGENT_INTEROP_SCRIPT = REPO_ROOT / "ops" / "agent-control" / "agent_interop_check.py"
WATCHDOG_SCRIPT = REPO_ROOT / "ops" / "watchdog" / "jvt_watchdog.py"
ORCHESTRATOR_SCRIPT = REPO_ROOT / "ops" / "agent-control" / "orchestrator.py"
VENTURE_PIPELINE_SCRIPT = REPO_ROOT / "ops" / "agent-control" / "venture_pipeline.py"
EOM_SCRIPT = REPO_ROOT / "ops" / "agent-control" / "eom_agent.py"
LOCAL_TASK_RUNNER_SCRIPT = REPO_ROOT / "ops" / "agent-control" / "local_task_runner.py"
FOLLOWUP_SCRIPT = REPO_ROOT / "outreach" / "tools" / "generate_followups.py"
DAILY_WAVE_SCRIPT = REPO_ROOT / "outreach" / "tools" / "generate_daily_wave.py"
ORCHESTRATOR_STATE = STATE_ROOT / "latest-orchestrator.json"
VOICE_QUALITY_ROOT = REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "jvt-inbound-voice-agent" / "voice-quality"

QUEUE_LABELS = ("draft", "review", "approved", "sent", "replied")
TASK_DIRS = ("pending", "running", "completed", "failed", "held")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def count_json(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def queue_counts() -> dict[str, int]:
    return {label: count_json(QUEUE_ROOT / label) for label in QUEUE_LABELS}


def run_step(name: str, command: list[str], timeout: int = 90) -> dict[str, Any]:
    started = time.time()
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
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
        "stdout_tail": result.stdout.strip().splitlines()[-8:],
        "stderr_tail": result.stderr.strip().splitlines()[-8:],
    }


def latest_followup_report() -> dict[str, Any]:
    if not FOLLOWUP_ROOT.exists():
        return {}
    reports = sorted(FOLLOWUP_ROOT.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return load_json(reports[0]) if reports else {}


def action_marker(name: str) -> Path:
    return STATE_ROOT / f"{date.today().isoformat()}-{name}.marker"


def write_marker(name: str, payload: dict[str, Any]) -> None:
    action_marker(name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def task_file_exists(task_id: str) -> bool:
    for folder in TASK_DIRS:
        if (TASK_ROOT / folder / f"{task_id}.json").exists():
            return True
    return False


def seed_daily_local_tasks() -> dict[str, Any]:
    today = date.today().isoformat()
    specs = [
        ("refresh-growth-state", "refresh_growth_state", "Refresh venture, orchestrator, EOM, and interop state."),
        ("content-backlog", "content_backlog_from_assets", "Refresh the internal content idea backlog from known proof/demo assets."),
        ("venture-scout-index", "venture_scout_index", "Refresh the venture scout report index."),
        ("offer-segment-summary", "offer_segment_summary", "Summarize existing AI receptionist and meeting-to-action prospect segments."),
        ("10k-execution-digest", "ten_k_execution_digest", "Generate the daily $10k-by-March-2027 execution digest."),
        ("paper-trader-refresh", "paper_trader_refresh", "Refresh paper-only trading account/backtest reports."),
    ]
    pending_root = TASK_ROOT / "pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    seeded: list[str] = []
    skipped: list[str] = []
    for suffix, task_type, goal in specs:
        task_id = f"{today}-{suffix}"
        if task_file_exists(task_id):
            skipped.append(task_id)
            continue
        payload = {
            "id": task_id,
            "type": task_type,
            "priority": "daily",
            "created_at": utc_now(),
            "goal": goal,
            "requires_approval": False,
            "seeded_by": "growth_ops_checkin",
        }
        (pending_root / f"{task_id}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        seeded.append(task_id)
    return {
        "name": "seed_daily_local_tasks",
        "ok": True,
        "returncode": 0,
        "duration_ms": 0,
        "seeded": seeded,
        "skipped": skipped,
        "stdout_tail": [f"seeded={len(seeded)} skipped={len(skipped)}"],
        "stderr_tail": [],
    }


def current_work_bucket(hours: int = 6) -> str:
    now = datetime.now(timezone.utc)
    bucket = (now.hour // hours) * hours
    return f"{now.date().isoformat()}-h{bucket:02d}"


def seed_workfeed_local_tasks(orchestrator: dict[str, Any]) -> dict[str, Any]:
    bucket = current_work_bucket()
    quotas = orchestrator.get("quotas") if isinstance(orchestrator.get("quotas"), dict) else {}
    work_items = orchestrator.get("work_items") if isinstance(orchestrator.get("work_items"), list) else []
    pending_root = TASK_ROOT / "pending"
    pending_root.mkdir(parents=True, exist_ok=True)

    specs: list[tuple[str, str, str, bool]] = [
        (
            "inbox-triage-brief",
            "inbox_triage_brief",
            "Create the internal brief for new inbox items and preserve the human-response decision gate.",
            int(quotas.get("inbox_new") or 0) > 0,
        ),
        (
            "outreach-review-queue-brief",
            "outreach_review_queue_brief",
            "Create the internal QA brief for review-queue packets so approval work has a concrete shortlist.",
            int(quotas.get("review_backlog") or 0) > 0,
        ),
        (
            "followup-review-brief",
            "followup_review_brief",
            "Create the internal QA brief for no-reply follow-up packets that need review.",
            int(quotas.get("eligible_followups") or 0) > 0,
        ),
    ]

    lanes = {str(item.get("lane") or "") for item in work_items if isinstance(item, dict)}
    if "offer-demos" in lanes or "venture-growth" in lanes:
        specs.append((
            "proof-asset-content-backlog",
            "content_backlog_from_assets",
            "Refresh internal proof-asset content ideas from current JVT demos and service wedges.",
            True,
        ))
    if any("Dental" in str(item.get("title") or item.get("detail") or "") for item in work_items if isinstance(item, dict)):
        specs.append((
            "dental-voice-pilot-brief",
            "dental_voice_intake_pilot_brief",
            "Refresh the internal dental voice-intake pilot brief from the current service wedge.",
            True,
        ))
    voice_samples = VOICE_QUALITY_ROOT / "samples"
    voice_renders = VOICE_QUALITY_ROOT / "renders"
    has_voice_samples = voice_samples.exists() and any(
        path.suffix.lower() in {".webm", ".wav", ".m4a", ".ogg", ".flac", ".mp3"}
        for path in voice_samples.glob("*")
        if path.is_file()
    )
    has_voice_renders = voice_renders.exists() and any(path.is_file() for path in voice_renders.glob("*"))
    if has_voice_samples and not has_voice_renders:
        specs.append((
            "voice-quality-sample-inventory",
            "voice_quality_sample_inventory",
            "Inventory consented voice samples and surface the missing local synthesis/evaluation step.",
            True,
        ))
    if any("ballot" in str(item.get("title") or item.get("detail") or "").lower() for item in work_items if isinstance(item, dict)):
        specs.append((
            "it-ballot-pilot-brief",
            "it_ballot_workflow_pilot_brief",
            "Refresh the internal IT ballot-workflow pilot brief from the current service wedge.",
            True,
        ))

    seeded: list[str] = []
    skipped: list[str] = []
    source_work_item_ids = [str(item.get("id")) for item in work_items[:8] if isinstance(item, dict) and item.get("id")]
    for suffix, task_type, goal, should_seed in specs:
        task_id = f"{bucket}-{suffix}"
        if not should_seed:
            skipped.append(task_id)
            continue
        if task_file_exists(task_id):
            skipped.append(task_id)
            continue
        payload = {
            "id": task_id,
            "type": task_type,
            "priority": "workfeed",
            "created_at": utc_now(),
            "goal": goal,
            "requires_approval": False,
            "seeded_by": "growth_ops_checkin_workfeed",
            "source_orchestrator_generated_at": orchestrator.get("generated_at"),
            "source_work_item_ids": source_work_item_ids,
            "safety_boundary": "Internal prep only. No external delivery, commitments, account changes, public posting, fund movement, or live-call setup.",
        }
        (pending_root / f"{task_id}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        seeded.append(task_id)

    return {
        "name": "seed_workfeed_local_tasks",
        "ok": True,
        "returncode": 0,
        "duration_ms": 0,
        "seeded": seeded,
        "skipped": skipped,
        "stdout_tail": [f"seeded={len(seeded)} skipped={len(skipped)} bucket={bucket}"],
        "stderr_tail": [],
    }


def refresh_core_state() -> list[dict[str, Any]]:
    steps = []
    steps.append(run_step("agent_interop", ["python3", str(AGENT_INTEROP_SCRIPT)], timeout=45))
    steps.append(run_step("watchdog", ["python3", str(WATCHDOG_SCRIPT)], timeout=120))
    steps.append(run_step("venture_pipeline", ["python3", str(VENTURE_PIPELINE_SCRIPT)], timeout=45))
    steps.append(run_step("orchestrator", ["python3", str(ORCHESTRATOR_SCRIPT)], timeout=45))
    steps.append(run_step("executive_ops_manager", ["python3", str(EOM_SCRIPT)], timeout=45))
    steps.append(seed_daily_local_tasks())
    steps.append(seed_workfeed_local_tasks(load_json(ORCHESTRATOR_STATE)))
    steps.append(run_step("local_task_runner", ["python3", str(LOCAL_TASK_RUNNER_SCRIPT), "--max-tasks", "6"], timeout=300))
    return steps


def safe_actions(orchestrator: dict[str, Any], *, dry_run: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    quotas = orchestrator.get("quotas") if isinstance(orchestrator.get("quotas"), dict) else {}
    queues = queue_counts()
    followup_review = 0
    for path in (QUEUE_ROOT / "review").glob("*.json") if (QUEUE_ROOT / "review").exists() else []:
        payload = load_json(path)
        if payload.get("follow_up_stage") or payload.get("follow_up_parent_stem"):
            followup_review += 1

    if FOLLOWUP_SCRIPT.exists():
        command = [
            "python3",
            str(FOLLOWUP_SCRIPT),
            "--root",
            str(REPO_ROOT),
            "--limit",
            "20",
        ]
        actions.append({
            "name": "refresh_followup_candidates",
            "type": "report-only",
            "result": {"ok": True, "dry_run": True} if dry_run else run_step("refresh_followup_candidates", command, timeout=60),
        })

    eligible_followups = int(quotas.get("eligible_followups") or 0)
    if (
        eligible_followups > 0
        and followup_review == 0
        and not action_marker("stage-followups").exists()
        and FOLLOWUP_SCRIPT.exists()
    ):
        command = [
            "python3",
            str(FOLLOWUP_SCRIPT),
            "--root",
            str(REPO_ROOT),
            "--limit",
            "5",
            "--output-queue",
            "review",
            "--write",
        ]
        result = {"ok": True, "dry_run": True, "reason": "would stage up to 5 follow-ups"} if dry_run else run_step("stage_followups", command, timeout=90)
        actions.append({"name": "stage_followups", "type": "stage-only", "result": result})
        if result.get("ok") and not dry_run:
            write_marker("stage-followups", result)

    if (
        queues.get("review", 0) == 0
        and queues.get("approved", 0) == 0
        and not action_marker("daily-wave").exists()
        and DAILY_WAVE_SCRIPT.exists()
    ):
        command = [
            "python3",
            str(DAILY_WAVE_SCRIPT),
            "--root",
            str(REPO_ROOT),
            "--packet-date",
            date.today().isoformat(),
            "--limit",
            "5",
            "--reply-to-email",
            "hello@jvt-technologies.com",
            "--site-url",
            "https://jvt-technologies.com",
            "--sender-name",
            "Chandru Vasudevan",
            "--sender-title",
            "Founder",
            "--sender-company",
            "JVT Technologies LLC",
        ]
        result = {"ok": True, "dry_run": True, "reason": "would stage up to 5 review packets"} if dry_run else run_step("stage_daily_wave", command, timeout=120)
        actions.append({"name": "stage_daily_wave", "type": "stage-only", "result": result})
        if result.get("ok") and not dry_run:
            write_marker("daily-wave", result)

    return actions


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# JVT Growth Ops Check-In",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Overall: `{'ok' if report.get('ok') else 'attention'}`",
        f"- Safety: {report.get('safety_boundary')}",
        "",
        "## Core Steps",
        "",
    ]
    for step in report.get("steps", []):
        lines.append(f"- `{'ok' if step.get('ok') else 'attention'}` {step.get('name')} ({step.get('duration_ms')} ms)")
    lines.extend(["", "## Safe Actions", ""])
    actions = report.get("safe_actions", [])
    if actions:
        for action in actions:
            result = action.get("result") or {}
            lines.append(f"- `{'ok' if result.get('ok') else 'attention'}` {action.get('name')} - {action.get('type')}")
    else:
        lines.append("- No safe actions were needed.")
    lines.extend(["", "## Top Work", ""])
    for item in report.get("top_work_items", []):
        lines.append(f"- P{item.get('priority')} `{item.get('lane')}` {item.get('title')}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def acquire_lock() -> int:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - LOCK_PATH.stat().st_mtime if LOCK_PATH.exists() else 0
        if age > 3600:
            LOCK_PATH.unlink(missing_ok=True)
            return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        raise SystemExit("Growth Ops check-in is already running.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the recurring JVT Growth Ops check-in.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lock_fd = acquire_lock()
    try:
        os.write(lock_fd, str(os.getpid()).encode("utf-8"))
        steps = refresh_core_state()
        orchestrator = load_json(ORCHESTRATOR_STATE)
        actions = safe_actions(orchestrator, dry_run=args.dry_run)
        if actions and not args.dry_run:
            steps.append(run_step("orchestrator_after_safe_actions", ["python3", str(ORCHESTRATOR_SCRIPT)], timeout=45))
            steps.append(run_step("executive_ops_manager_after_safe_actions", ["python3", str(EOM_SCRIPT)], timeout=45))
            steps.append(run_step("local_task_runner_after_safe_actions", ["python3", str(LOCAL_TASK_RUNNER_SCRIPT), "--max-tasks", "2"], timeout=300))
            orchestrator = load_json(ORCHESTRATOR_STATE)

        top_work = (orchestrator.get("work_items") or [])[:8] if isinstance(orchestrator, dict) else []
        report = {
            "generated_at": utc_now(),
            "ok": all(step.get("ok") for step in steps) and all((action.get("result") or {}).get("ok") for action in actions),
            "dry_run": args.dry_run,
            "steps": steps,
            "safe_actions": actions,
            "queue_counts": queue_counts(),
            "latest_followup_report": latest_followup_report(),
            "orchestrator_status": orchestrator.get("status") if isinstance(orchestrator, dict) else "missing",
            "top_work_items": top_work,
            "safety_boundary": "No sends, auto-approvals, spend, provider commitments, live trades, wallets, mining, staking, or custody actions.",
        }
        json_path = STATE_ROOT / "latest-growth-ops-checkin.json"
        markdown_path = STATE_ROOT / "latest-growth-ops-checkin.md"
        json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        write_markdown(report, markdown_path)
        print(json.dumps({"ok": report["ok"], "json_path": str(json_path), "markdown_path": str(markdown_path)}))
    finally:
        os.close(lock_fd)
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"ok": False, "error": f"Timed out: {exc}"}), file=sys.stderr)
        raise
