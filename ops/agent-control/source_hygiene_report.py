#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_ROOT = REPO_ROOT / "ops" / "agent-control" / "state"
REPORT_JSON = STATE_ROOT / "latest-source-hygiene.json"
REPORT_MD = STATE_ROOT / "latest-source-hygiene.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_git(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=45, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def classify(lines: list[str]) -> dict[str, int]:
    counts = {"modified": 0, "added": 0, "deleted": 0, "renamed": 0, "untracked": 0, "other": 0}
    for line in lines:
        code = line[:2]
        if code == "??":
            counts["untracked"] += 1
        elif "D" in code:
            counts["deleted"] += 1
        elif "R" in code:
            counts["renamed"] += 1
        elif "A" in code:
            counts["added"] += 1
        elif "M" in code:
            counts["modified"] += 1
        else:
            counts["other"] += 1
    return counts


def build_report() -> dict[str, Any]:
    status_code, status_out, status_err = run_git(["status", "--short"])
    branch_code, branch_out, branch_err = run_git(["branch", "--show-current"])
    lines = [line for line in status_out.splitlines() if line.strip()]
    counts = classify(lines)
    important_prefixes = (
        "ops/agent-control/",
        "ops/control-panel/",
        "outreach/tools/",
        "lead-pipeline/tools/",
        "products/Private-AI-Lab/apps/jvt-inbound-voice-agent/",
    )
    important = [
        line
        for line in lines
        if any(line[3:].startswith(prefix) if len(line) > 3 else False for prefix in important_prefixes)
    ]
    return {
        "generated_at": utc_now(),
        "ok": status_code == 0 and branch_code == 0,
        "branch": branch_out or "",
        "status_count": len(lines),
        "counts": counts,
        "important_changes": important[:80],
        "status_sample": lines[:120],
        "stderr": status_err or branch_err,
        "next_action": "Review and group the dirty tree before deployment/PR work. Do not reset or discard user changes.",
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# JVT Source Hygiene",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Branch: `{report.get('branch') or 'unknown'}`",
        f"- Dirty entries: `{report['status_count']}`",
        f"- Next: {report['next_action']}",
        "",
        "## Counts",
        "",
    ]
    for key, value in sorted((report.get("counts") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Important Changes", ""])
    if report.get("important_changes"):
        lines.extend(f"- `{line}`" for line in report["important_changes"])
    else:
        lines.append("- None.")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    write_json(REPORT_JSON, report)
    write_markdown(report)
    print(json.dumps({"ok": report["ok"], "dirty": report["status_count"], "branch": report.get("branch")}))


if __name__ == "__main__":
    main()
