#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_ROOT = REPO_ROOT / "ops" / "agent-control" / "state"
REPORT_JSON = STATE_ROOT / "latest-system-resources.json"
REPORT_MD = STATE_ROOT / "latest-system-resources.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(command: list[str], timeout: int = 20) -> dict[str, Any]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return {"ok": result.returncode == 0, "returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except Exception as exc:
        return {"ok": False, "error": repr(exc), "stdout": "", "stderr": ""}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_df(stdout: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        rows.append({
            "filesystem": parts[0],
            "size": parts[1],
            "used": parts[2],
            "available": parts[3],
            "capacity": parts[4],
            "mounted_on": parts[-1],
        })
    return rows


def build_report() -> dict[str, Any]:
    disk = run(["df", "-h", "/"])
    pmset = run(["pmset", "-g", "batt"])
    vm_stat = run(["vm_stat"])
    netstat = run(["netstat", "-an", "-p", "tcp"])
    tcp_lines = netstat.get("stdout", "").splitlines()
    time_wait = sum(1 for line in tcp_lines if "TIME_WAIT" in line)
    close_wait = sum(1 for line in tcp_lines if "CLOSE_WAIT" in line)
    syn_sent = sum(1 for line in tcp_lines if "SYN_SENT" in line)
    disk_rows = parse_df(disk.get("stdout", ""))
    findings: list[str] = []
    if disk_rows:
        capacity = disk_rows[0].get("capacity", "0%").rstrip("%")
        try:
            if int(capacity) >= 85:
                findings.append("Root disk is above 85 percent used.")
        except ValueError:
            pass
    if "AC Power" not in pmset.get("stdout", ""):
        findings.append("M4 does not report AC power.")
    if time_wait > 3000:
        findings.append("High TIME_WAIT socket count.")
    if close_wait > 100:
        findings.append("High CLOSE_WAIT socket count.")
    return {
        "generated_at": utc_now(),
        "ok": not findings,
        "disk": disk_rows,
        "power_summary": pmset.get("stdout", "").splitlines()[:4],
        "tcp": {
            "time_wait": time_wait,
            "close_wait": close_wait,
            "syn_sent": syn_sent,
        },
        "vm_stat_tail": vm_stat.get("stdout", "").splitlines()[-12:],
        "findings": findings,
        "next_action": "Keep JVT services on M4, but hold volume expansion if power, disk, or TCP pressure reports warning-level findings.",
    }


def write_markdown(report: dict[str, Any]) -> None:
    disk = (report.get("disk") or [{}])[0]
    tcp = report.get("tcp") or {}
    lines = [
        "# JVT M4 System Resources",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Overall: `{'ok' if report.get('ok') else 'attention'}`",
        f"- Disk: `{disk.get('used', 'unknown')}` used / `{disk.get('available', 'unknown')}` free / `{disk.get('capacity', 'unknown')}` capacity",
        f"- TCP TIME_WAIT: `{tcp.get('time_wait')}`",
        f"- TCP CLOSE_WAIT: `{tcp.get('close_wait')}`",
        f"- TCP SYN_SENT: `{tcp.get('syn_sent')}`",
        "",
        "## Findings",
        "",
    ]
    if report.get("findings"):
        lines.extend(f"- {item}" for item in report["findings"])
    else:
        lines.append("- No findings.")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    write_json(REPORT_JSON, report)
    write_markdown(report)
    print(json.dumps({"ok": report["ok"], "findings": len(report["findings"]), "tcp": report["tcp"]}))


if __name__ == "__main__":
    main()
