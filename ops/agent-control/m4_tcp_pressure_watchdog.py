#!/usr/bin/env python3
"""Record and optionally manage M4 TCP pressure affecting JVT health checks.

This intentionally runs without sudo. Kernel tuning is handled separately by
`m4_tcp_tuning_root.sh`, because sysctl writes require administrator privileges.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "ops" / "agent-control" / "state"
LOG_DIR = ROOT / "ops" / "agent-control" / "logs"

CHECK_PORTS = {
    "m4_mlx_model": 11435,
    "control_panel": 8042,
    "voice_intake": 8066,
    "private_doc_demo": 8000,
}

MANAGED_LABELS = {
    "whisper_large": "org.ntc.whisper-large-server",
    "homeagent_bridge": "com.daynadante.homeagent.bridge",
    "translation_tts": "org.ntc.translation-tts-server",
    "m4_mlx_model": "com.jvt.m4-mlx-model-server",
}

STATE_TOKENS = {
    "LISTEN",
    "ESTABLISHED",
    "SYN_SENT",
    "SYN_RECEIVED",
    "FIN_WAIT_1",
    "FIN_WAIT_2",
    "CLOSE_WAIT",
    "CLOSING",
    "LAST_ACK",
    "TIME_WAIT",
    "CLOSED",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_command(*command: str, timeout: int = 20) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": list(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except Exception as exc:  # pragma: no cover - defensive host tooling path
        return {
            "command": list(command),
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def redact_sensitive(text: str) -> str:
    redacted_lines = []
    sensitive_names = ("TOKEN", "SECRET", "PASSWORD", "PASS", "API_KEY", "KEY")
    for line in text.splitlines():
        if "=>" in line:
            name = line.split("=>", 1)[0].strip().upper()
            if any(marker in name for marker in sensitive_names):
                redacted_lines.append(line.split("=>", 1)[0] + "=> <redacted>")
                continue
        redacted_lines.append(line)
    return "\n".join(redacted_lines)


def read_sysctl() -> dict[str, str]:
    keys = [
        "net.inet.tcp.msl",
        "net.inet.ip.portrange.first",
        "net.inet.ip.portrange.last",
    ]
    result = run_command("sysctl", *keys)
    values: dict[str, str] = {}
    for line in result["stdout"].splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            values[key.strip()] = value.strip()
    return values


def parse_tcp_table() -> dict[str, Any]:
    result = run_command("netstat", "-anv", "-p", "tcp", timeout=45)
    state_counts: Counter[str] = Counter()
    loopback_state_counts: Counter[str] = Counter()
    process_state_counts: dict[str, Counter[str]] = defaultdict(Counter)
    top_rows: list[dict[str, str]] = []

    for line in result["stdout"].splitlines():
        tokens = line.split()
        if len(tokens) < 6 or not tokens[0].startswith("tcp"):
            continue
        state = tokens[5]
        if state not in STATE_TOKENS:
            continue
        local = tokens[3]
        foreign = tokens[4]
        process = tokens[10] if len(tokens) > 10 else ""
        state_counts[state] += 1
        process_state_counts[process][state] += 1
        if "127.0.0.1" in local or "127.0.0.1" in foreign or "::1" in local or "::1" in foreign:
            loopback_state_counts[state] += 1
        if state in {"SYN_SENT", "FIN_WAIT_1", "LAST_ACK", "TIME_WAIT"} and len(top_rows) < 60:
            top_rows.append(
                {
                    "proto": tokens[0],
                    "local": local,
                    "foreign": foreign,
                    "state": state,
                    "process": process,
                }
            )

    processes = []
    for process, counts in process_state_counts.items():
        total = sum(counts.values())
        if total < 5 and not any(counts.get(s, 0) for s in ("SYN_SENT", "FIN_WAIT_1", "LAST_ACK")):
            continue
        processes.append(
            {
                "process": process or "(unknown)",
                "total": total,
                "states": dict(counts),
            }
        )
    processes.sort(key=lambda item: item["total"], reverse=True)

    return {
        "command_returncode": result["returncode"],
        "command_stderr": result["stderr"].strip(),
        "states": dict(state_counts),
        "loopback_states": dict(loopback_state_counts),
        "top_processes": processes[:25],
        "sample_pressure_rows": top_rows,
    }


def parse_mbufs() -> dict[str, Any]:
    result = run_command("netstat", "-m")
    text = result["stdout"]
    network_match = re.search(r"(\d+) KB allocated to network \(([\d.]+)% in use\)", text)
    denied_match = re.search(r"(\d+) requests for memory denied", text)
    mbuf_match = re.search(r"(\d+)/(\d+) mbufs in use", text)
    return {
        "command_returncode": result["returncode"],
        "network_kb": int(network_match.group(1)) if network_match else None,
        "network_percent_in_use": float(network_match.group(2)) if network_match else None,
        "memory_denied_requests": int(denied_match.group(1)) if denied_match else None,
        "mbufs_in_use": int(mbuf_match.group(1)) if mbuf_match else None,
        "mbufs_total": int(mbuf_match.group(2)) if mbuf_match else None,
        "raw_head": "\n".join(text.splitlines()[:12]),
    }


def check_loopback_ports() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for name, port in CHECK_PORTS.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", port))
            checks[name] = {"port": port, "ok": True, "error": None}
        except Exception as exc:
            checks[name] = {
                "port": port,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        finally:
            sock.close()
    return checks


def launchctl_print(label: str) -> dict[str, Any]:
    result = run_command("launchctl", "print", f"gui/{os.getuid()}/{label}")
    state = {
        "label": label,
        "loaded": result["returncode"] == 0,
        "raw": redact_sensitive(result["stdout"][-3000:]),
    }
    pid_match = re.search(r"\bpid = (\d+)", result["stdout"])
    status_match = re.search(r"\blast exit status = ([^\n]+)", result["stdout"])
    if pid_match:
        state["pid"] = int(pid_match.group(1))
    if status_match:
        state["last_exit_status"] = status_match.group(1).strip()
    if result["stderr"].strip():
        state["stderr"] = result["stderr"].strip()
    return state


def managed_service_status() -> dict[str, Any]:
    return {name: launchctl_print(label) for name, label in MANAGED_LABELS.items()}


def restart_managed_services(names: list[str]) -> list[dict[str, Any]]:
    actions = []
    for name in names:
        label = MANAGED_LABELS.get(name)
        if not label:
            actions.append({"name": name, "ok": False, "error": "unknown managed service"})
            continue
        result = run_command("launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}", timeout=20)
        actions.append(
            {
                "name": name,
                "label": label,
                "returncode": result["returncode"],
                "stdout": result["stdout"].strip(),
                "stderr": result["stderr"].strip(),
            }
        )
    return actions


def load_previous_report() -> dict[str, Any] | None:
    path = STATE_DIR / "latest-m4-tcp-pressure.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def int_sysctl_value(values: dict[str, str], key: str) -> int | None:
    try:
        return int(values.get(key, ""))
    except ValueError:
        return None


def tcp_tuning_status(values: dict[str, str]) -> dict[str, Any]:
    msl = int_sysctl_value(values, "net.inet.tcp.msl")
    port_first = int_sysctl_value(values, "net.inet.ip.portrange.first")
    port_last = int_sysctl_value(values, "net.inet.ip.portrange.last")
    ok = (
        msl is not None
        and port_first is not None
        and port_last is not None
        and msl <= 5000
        and port_first <= 10000
        and port_last >= 65535
    )
    return {
        "ok": ok,
        "expected": {
            "net.inet.tcp.msl": "<=5000",
            "net.inet.ip.portrange.first": "<=10000",
            "net.inet.ip.portrange.last": ">=65535",
        },
    }


def add_mbuf_trend(report: dict[str, Any], previous: dict[str, Any] | None) -> None:
    current_denied = report["mbufs"].get("memory_denied_requests")
    previous_denied = None
    if previous:
        previous_denied = previous.get("mbufs", {}).get("memory_denied_requests")
    if isinstance(current_denied, int) and isinstance(previous_denied, int):
        report["mbufs"]["previous_memory_denied_requests"] = previous_denied
        report["mbufs"]["memory_denied_delta"] = max(0, current_denied - previous_denied)
    else:
        report["mbufs"]["previous_memory_denied_requests"] = previous_denied
        report["mbufs"]["memory_denied_delta"] = None


def severity(report: dict[str, Any]) -> str:
    tcp_states = report["tcp"]["states"]
    mbufs = report["mbufs"]
    loopback_checks = report["loopback_checks"]
    failed_loopback = [name for name, check in loopback_checks.items() if not check["ok"]]
    network_percent = mbufs.get("network_percent_in_use")
    denied = mbufs.get("memory_denied_requests") or 0
    denied_delta = mbufs.get("memory_denied_delta")
    time_wait = tcp_states.get("TIME_WAIT", 0)
    syn_sent = tcp_states.get("SYN_SENT", 0)

    if failed_loopback:
        return "critical"
    if denied_delta is not None and denied_delta > 0:
        return "critical"
    if network_percent is not None and network_percent >= 95:
        return "critical"
    if syn_sent >= 500:
        return "critical"
    if (
        not report.get("tcp_tuning", {}).get("ok")
        or denied > 0
        or syn_sent >= 100
        or (network_percent is not None and network_percent >= 75)
        or time_wait >= 10000
    ):
        return "warning"
    return "ok"


def write_report(report: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    json_path = STATE_DIR / "latest-m4-tcp-pressure.json"
    md_path = STATE_DIR / "latest-m4-tcp-pressure.md"
    history_path = LOG_DIR / "m4-tcp-pressure.jsonl"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    with history_path.open("a") as handle:
        handle.write(json.dumps(report, sort_keys=True) + "\n")

    states = report["tcp"]["states"]
    loopback = report["loopback_checks"]
    top_processes = report["tcp"]["top_processes"][:8]
    lines = [
        "# M4 TCP Pressure",
        "",
        f"- Checked: `{report['checked_at']}`",
        f"- Severity: `{report['severity']}`",
        f"- Sysctl: `{report['sysctl']}`",
        f"- TCP tuning active: `{report.get('tcp_tuning', {}).get('ok')}`",
        f"- TCP states: `{states}`",
        f"- Loopback states: `{report['tcp']['loopback_states']}`",
        f"- Mbuf network use: `{report['mbufs'].get('network_percent_in_use')}%`",
        f"- Mbuf denied requests: `{report['mbufs'].get('memory_denied_requests')}`",
        f"- Mbuf denied delta: `{report['mbufs'].get('memory_denied_delta')}`",
        "",
        "## Loopback Health",
    ]
    for name, check in loopback.items():
        status = "ok" if check["ok"] else f"failed: {check['error']}"
        lines.append(f"- `{name}` port `{check['port']}`: {status}")
    lines.extend(["", "## Top Processes"])
    for process in top_processes:
        lines.append(f"- `{process['process']}` total `{process['total']}` states `{process['states']}`")
    if report.get("actions"):
        lines.extend(["", "## Actions"])
        for action in report["actions"]:
            lines.append(f"- `{action.get('name')}` returncode `{action.get('returncode')}` stderr `{action.get('stderr')}`")
    md_path.write_text("\n".join(lines) + "\n")


def build_report(actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    previous = load_previous_report()
    report = {
        "checked_at": utc_now(),
        "host": socket.gethostname(),
        "sysctl": read_sysctl(),
        "tcp": parse_tcp_table(),
        "mbufs": parse_mbufs(),
        "loopback_checks": check_loopback_ports(),
        "managed_services": managed_service_status(),
        "actions": actions or [],
    }
    report["tcp_tuning"] = tcp_tuning_status(report["sysctl"])
    add_mbuf_trend(report, previous)
    report["severity"] = severity(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--restart-managed-services",
        nargs="*",
        choices=sorted(MANAGED_LABELS),
        help="Optionally kickstart selected user LaunchAgents after recording pressure.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    actions: list[dict[str, Any]] = []
    if args.restart_managed_services is not None:
        names = args.restart_managed_services or ["m4_mlx_model"]
        actions = restart_managed_services(names)

    report = build_report(actions)
    write_report(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"{report['checked_at']} severity={report['severity']} "
            f"states={report['tcp']['states']} "
            f"mbuf={report['mbufs'].get('network_percent_in_use')}% "
            f"loopback_ok={all(c['ok'] for c in report['loopback_checks'].values())}"
        )
    return 0 if report["severity"] != "critical" else 2


if __name__ == "__main__":
    sys.exit(main())
