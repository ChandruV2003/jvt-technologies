#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
STATE_ROOT = ROOT / "ops" / "watchdog" / "state"
QUEUE_ROOT = ROOT / "outreach" / "queue"
INBOX_ROOT = ROOT / "outreach" / "inbox"
LEAD_STATUS = ROOT / "lead-pipeline" / "state" / "auto-research-status.md"
MAILBOX_LOG = ROOT / "outreach" / "mailbox-agent" / "state" / "mailbox-listener.out.log"
SERVICE_BOARD = ROOT / "strategy" / "service-line-execution-board.json"
ORCHESTRATOR_STATE = ROOT / "ops" / "agent-control" / "state" / "latest-orchestrator.json"
GROWTH_CHECKIN_STATE = ROOT / "ops" / "agent-control" / "state" / "latest-growth-ops-checkin.json"
PUBLIC_CONVERSION_KV_SYNC_STATE = ROOT / "ops" / "agent-control" / "state" / "latest-public-conversion-kv-sync.json"
TRADER_ROOT = Path("/Users/c.s.d.v.r.s./Developer/JVT-AutoTrader")
DEBIAN_TRADER_HOST = "macmini-i7-debian"
DEBIAN_TRADER_ROOT = "/home/sysadmin/JVT-AutoTrader"

HTTP_CHECKS = {
    "public_site": "https://jvt-technologies.com/",
    "control_panel": "http://127.0.0.1:8042/health",
    "voice_intake": "http://127.0.0.1:8066/health",
}

LAUNCH_LABELS = [
    "com.jvt.control-panel",
    "com.jvt.orchestrator",
    "com.jvt.growth-ops-checkin",
    "com.jvt.inbound-voice-agent",
    "com.jvt.mailbox-listener",
    "com.jvt.lead-research",
    "com.jvt.daily-wave-prep",
    "com.jvt.private-doc-intel-demo",
    "com.jvt.public-conversion-kv-sync",
]


def utcish_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def count_json(directory: Path, recursive: bool = False) -> int:
    if not directory.exists():
        return 0
    iterator = directory.rglob("*.json") if recursive else directory.glob("*.json")
    return sum(1 for path in iterator if path.is_file())


def check_http(name: str, url: str) -> dict[str, object]:
    started = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JVT-Watchdog/1.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            body = response.read(200_000).decode("utf-8", "ignore")
        status = int(response.status)
        ok = 200 <= status < 400
        if name == "public_site":
            lowered = body.lower()
            current_markers = ("workflow", "intake", "demo", "document")
            ok = ok and "jvt technologies" in lowered and any(marker in lowered for marker in current_markers)
        return {
            "ok": ok,
            "status": status,
            "latency_ms": int((time.time() - started) * 1000),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "latency_ms": int((time.time() - started) * 1000),
        }


def launchctl_status() -> dict[str, dict[str, object]]:
    try:
        proc = subprocess.run(["launchctl", "list"], check=False, capture_output=True, text=True, timeout=8)
    except Exception as exc:
        return {label: {"ok": False, "error": str(exc)} for label in LAUNCH_LABELS}

    rows: dict[str, dict[str, object]] = {}
    for raw in proc.stdout.splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        pid, last_status, label = parts[0], parts[1], parts[2]
        if label in LAUNCH_LABELS:
            rows[label] = {
                "ok": pid != "-" or last_status == "0",
                "pid": pid,
                "last_status": last_status,
            }
    for label in LAUNCH_LABELS:
        rows.setdefault(label, {"ok": False, "missing": True})
    return rows


def approved_qc_issues() -> list[dict[str, object]]:
    sys.path.insert(0, str((ROOT / "outreach" / "tools").resolve()))
    try:
        import auto_review_wave
    except Exception as exc:
        return [{"stem": "__validator_import__", "issues": [str(exc)]}]

    issues: list[dict[str, object]] = []
    for path in sorted((QUEUE_ROOT / "approved").glob("*.json")):
        packet_issues = auto_review_wave.validate_packet(path.stem, "approved")
        if packet_issues:
            issues.append({"stem": path.stem, "issues": packet_issues})
    return issues


def service_board_status() -> dict[str, object]:
    if not SERVICE_BOARD.exists():
        return {"ok": False, "missing": True, "blocked": [], "next_count": 0}
    data = json.loads(SERVICE_BOARD.read_text())
    wedges = data.get("wedges", [])
    blocked = [
        wedge.get("id")
        for wedge in wedges
        if str(wedge.get("status", "")).lower() in {"blocked", "stalled"}
    ]
    next_count = sum(len(wedge.get("next_actions", [])) for wedge in wedges)
    return {
        "ok": not blocked and next_count > 0,
        "wedge_count": len(wedges),
        "blocked": blocked,
        "next_count": next_count,
    }


def public_conversion_kv_sync_status() -> dict[str, object]:
    age = file_age_seconds(PUBLIC_CONVERSION_KV_SYNC_STATE)
    if not PUBLIC_CONVERSION_KV_SYNC_STATE.exists():
        return {
            "ok": False,
            "missing": True,
            "age_seconds": None,
            "failed_count": 0,
            "unreconciled_count": 0,
        }
    try:
        payload = json.loads(PUBLIC_CONVERSION_KV_SYNC_STATE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "age_seconds": age,
            "error": str(exc),
            "failed_count": 1,
            "unreconciled_count": 0,
        }
    return {
        "ok": bool(payload.get("ok")) and age is not None and age <= 900,
        "age_seconds": age,
        "generated_at": payload.get("generated_at"),
        "remote_key_count": int(payload.get("remote_key_count") or 0),
        "checkpointed_key_count": int(payload.get("checkpointed_key_count") or 0),
        "failed_count": int(payload.get("failed_count") or 0),
        "unreconciled_count": int(payload.get("unreconciled_count") or 0),
        "max_handoff_lag_seconds": payload.get("max_handoff_lag_seconds"),
    }


def trader_status() -> dict[str, object]:
    snapshot = TRADER_ROOT / "state" / "latest_account_snapshot.json"
    backtest = TRADER_ROOT / "state" / "latest_backtest.json"
    paper_bot = TRADER_ROOT / "state" / "latest_paper_bot_report.json"
    snapshot_age = file_age_seconds(snapshot)
    backtest_age = file_age_seconds(backtest)
    paper_bot_age = file_age_seconds(paper_bot)
    local_ok = all(
        age is not None and age < 24 * 3600
        for age in (snapshot_age, backtest_age, paper_bot_age)
    )
    remote: dict[str, object] = {"ok": False, "host": DEBIAN_TRADER_HOST}
    try:
        proc = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                DEBIAN_TRADER_HOST,
                f"cd {DEBIAN_TRADER_ROOT} && .venv/bin/python - <<'PY'\n"
                "import json, os, time\n"
                "from pathlib import Path\n"
                "root = Path('.')\n"
                "state = root / 'state'\n"
                "def age(path):\n"
                "    return None if not path.exists() else max(0, time.time() - path.stat().st_mtime)\n"
                "def read(path):\n"
                "    return json.loads(path.read_text()) if path.exists() else None\n"
                "env = root / '.env'\n"
                "env_text = env.read_text() if env.exists() else ''\n"
                "paper_key = any(line.startswith('APCA_API_KEY_ID=') and line.split('=', 1)[1].strip() for line in env_text.splitlines())\n"
                "paper_secret = any(line.startswith('APCA_API_SECRET_KEY=') and line.split('=', 1)[1].strip() for line in env_text.splitlines())\n"
                "bot = read(state / 'latest_paper_bot_report.json') or {}\n"
                "sim = read(state / 'latest_micro_simulation.json') or {}\n"
                "print(json.dumps({\n"
                "    'ok': True,\n"
                "    'host': os.uname().nodename,\n"
                "    'has_env': env.exists(),\n"
                "    'has_venv': (root / '.venv').exists(),\n"
                "    'paper_credentials_configured': bool(paper_key and paper_secret),\n"
                "    'offline_report_age_seconds': age(state / 'latest_paper_bot_report.json'),\n"
                "    'micro_simulation_age_seconds': age(state / 'latest_micro_simulation.json'),\n"
                "    'offline_mode': bot.get('mode'),\n"
                "    'offline_submitted_count': bot.get('submitted_count'),\n"
                "    'offline_plan_count': len(bot.get('plans') or []),\n"
                "    'simulation_return_pct': sim.get('return_pct'),\n"
                "    'required_return_to_10000_pct': sim.get('required_return_to_10000_pct'),\n"
                "}))\n"
                "PY",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            remote = json.loads(proc.stdout)
        else:
            remote = {
                "ok": False,
                "host": DEBIAN_TRADER_HOST,
                "error": (proc.stderr or proc.stdout or "no trader status output").strip(),
            }
    except Exception as exc:
        remote = {"ok": False, "host": DEBIAN_TRADER_HOST, "error": str(exc)}

    return {
        "ok": local_ok,
        "paper_snapshot_age_seconds": snapshot_age,
        "backtest_age_seconds": backtest_age,
        "paper_bot_age_seconds": paper_bot_age,
        "has_snapshot": snapshot.exists(),
        "has_backtest": backtest.exists(),
        "has_paper_bot_report": paper_bot.exists(),
        "local_guardrail": "Fresh local paper-only artifacts are authoritative. Debian mirror status is supplemental.",
        "debian": remote,
    }


def build_report() -> dict[str, object]:
    http = {name: check_http(name, url) for name, url in HTTP_CHECKS.items()}
    launchd = launchctl_status()
    qc_issues = approved_qc_issues()
    mailbox_age = file_age_seconds(MAILBOX_LOG)
    lead_age = file_age_seconds(LEAD_STATUS)
    orchestrator_age = file_age_seconds(ORCHESTRATOR_STATE)
    growth_checkin_age = file_age_seconds(GROWTH_CHECKIN_STATE)

    queue_counts = {
        label: count_json(QUEUE_ROOT / label)
        for label in ["draft", "review", "approved", "sent", "replied"]
    }
    inbox_counts = {
        "new": count_json(INBOX_ROOT / "new", recursive=True),
        "reviewed": count_json(INBOX_ROOT / "reviewed", recursive=True),
        "closed": count_json(INBOX_ROOT / "closed", recursive=True),
    }

    findings: list[dict[str, str]] = []
    for name, result in http.items():
        if not result.get("ok"):
            findings.append({"severity": "critical", "area": name, "message": "HTTP health check failed"})
    for label, result in launchd.items():
        if not result.get("ok"):
            findings.append({"severity": "warning", "area": label, "message": "Launch agent is not cleanly running"})
    if mailbox_age is None or mailbox_age > 900:
        findings.append({"severity": "warning", "area": "mailbox-listener", "message": "Mailbox log is stale or missing"})
    if lead_age is None or lead_age > 4 * 3600:
        findings.append({"severity": "warning", "area": "lead-research", "message": "Lead research status is stale or missing"})
    if orchestrator_age is None or orchestrator_age > 2 * 3600:
        findings.append({"severity": "warning", "area": "orchestrator", "message": "Growth OS orchestrator state is stale or missing"})
    if growth_checkin_age is None or growth_checkin_age > 2 * 3600:
        findings.append({"severity": "warning", "area": "growth-ops-checkin", "message": "Growth Ops check-in state is stale or missing"})
    if qc_issues:
        findings.append({"severity": "critical", "area": "outreach-qc", "message": f"{len(qc_issues)} approved packet(s) failed QC"})
    if inbox_counts["new"] > 0:
        findings.append({"severity": "notice", "area": "inbox", "message": f"{inbox_counts['new']} new inbox item(s) need triage"})

    service_board = service_board_status()
    if not service_board.get("ok"):
        findings.append({"severity": "warning", "area": "service-lines", "message": "Service-line execution board is missing or blocked"})
    public_conversion_kv_sync = public_conversion_kv_sync_status()
    if not public_conversion_kv_sync.get("ok"):
        findings.append({
            "severity": "critical",
            "area": "public-conversion-kv-sync",
            "message": "Public workflow-intake synchronization is stale, failed, or missing",
        })
    elif int(public_conversion_kv_sync.get("unreconciled_count") or 0):
        findings.append({
            "severity": "critical",
            "area": "public-conversion-kv-sync",
            "message": f"{public_conversion_kv_sync.get('unreconciled_count')} public intake record(s) are unreconciled",
        })

    return {
        "generated_at": utcish_now(),
        "overall_ok": not any(item["severity"] == "critical" for item in findings),
        "http": http,
        "launchd": launchd,
        "queue_counts": queue_counts,
        "inbox_counts": inbox_counts,
        "approved_qc_issue_count": len(qc_issues),
        "approved_qc_issues": qc_issues[:20],
        "mailbox_log_age_seconds": mailbox_age,
        "lead_status_age_seconds": lead_age,
        "orchestrator_state_age_seconds": orchestrator_age,
        "growth_checkin_state_age_seconds": growth_checkin_age,
        "service_board": service_board,
        "public_conversion_kv_sync": public_conversion_kv_sync,
        "trader": trader_status(),
        "findings": findings,
    }


def render_markdown(report: dict[str, object]) -> str:
    findings = report["findings"]
    lines = [
        "# JVT Watchdog Status",
        "",
        f"Generated: {report['generated_at']}",
        f"Overall OK: {report['overall_ok']}",
        "",
        "## Findings",
    ]
    if findings:
        for finding in findings:
            lines.append(f"- {finding['severity']}: {finding['area']} - {finding['message']}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Queues",
            f"- outreach: {report['queue_counts']}",
            f"- inbox: {report['inbox_counts']}",
            f"- approved QC issue count: {report['approved_qc_issue_count']}",
            "",
            "## Service Lines",
            f"- board: {report['service_board']}",
            "",
            "## Public Conversion Sync",
            f"- KV sync: {report['public_conversion_kv_sync']}",
            "",
            "## Trader Research",
            f"- paper trader: {report['trader']}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    report = build_report()
    (STATE_ROOT / "latest-watchdog.json").write_text(json.dumps(report, indent=2) + "\n")
    (STATE_ROOT / "latest-watchdog.md").write_text(render_markdown(report) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
