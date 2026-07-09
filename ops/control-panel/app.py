#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import os
import re
import shlex
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from pathlib import Path
from threading import Lock
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
REPO_ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
LEAD_DB = REPO_ROOT / "lead-pipeline" / "data" / "jvt_leads.sqlite3"
OUTREACH_QUEUE = REPO_ROOT / "outreach" / "queue"
OUTREACH_SCHEDULES = REPO_ROOT / "outreach" / "schedules"
OUTREACH_ENV_FILE = REPO_ROOT / "outreach" / ".env.local"
INBOX_ROOT = REPO_ROOT / "outreach" / "inbox"
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
AGENT_ROOT = CONTROL_ROOT / "agents"
RESEARCH_STATE_PATH = REPO_ROOT / "lead-pipeline" / "state" / "auto-research-state.json"
REVENUE_OPPORTUNITIES_PATH = REPO_ROOT / "strategy" / "revenue-opportunities.json"
WATCHDOG_STATE_PATH = REPO_ROOT / "ops" / "watchdog" / "state" / "latest-watchdog.json"
TCP_PRESSURE_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-m4-tcp-pressure.json"
AUTO_SEND_STATE_PATH = REPO_ROOT / "outreach" / "schedules" / "auto-send" / "latest-auto-send.json"
OPERATOR_ALERTS_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "operator-notifier" / "latest-alerts.json"
AGENT_INTEROP_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-agent-interop.json"
ORCHESTRATOR_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-orchestrator.json"
GROWTH_CHECKIN_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-growth-ops-checkin.json"
OPPORTUNITY_MANAGER_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-opportunity-manager.json"
VOICE_READINESS_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-voice-readiness.json"
PAPER_TRADER_HEALTH_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-paper-trader-health.json"
SOURCE_HYGIENE_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-source-hygiene.json"
SYSTEM_RESOURCES_STATE_PATH = REPO_ROOT / "ops" / "agent-control" / "state" / "latest-system-resources.json"
FOLLOWUP_REPORT_DIR = REPO_ROOT / "outreach" / "schedules" / "followups"
CRYPTO_LAB_ROOT = Path(os.environ.get("JVT_CRYPTO_LAB_ROOT", "/Users/c.s.d.v.r.s./Developer/JVT-Crypto-Intelligence-Lab"))
CRYPTO_LAB_REPORT = CRYPTO_LAB_ROOT / "reports" / "latest-feasibility.json"
CRYPTO_LAB_HTML = CRYPTO_LAB_ROOT / "site" / "index.html"
CRYPTO_LAB_SCRIPT = CRYPTO_LAB_ROOT / "scripts" / "run_feasibility.py"
CRYPTO_LAB_CONFIG = CRYPTO_LAB_ROOT / "config" / "lab-assumptions.json"
CLIENT_REGISTRY = Path("/Users/c.s.d.v.r.s./Documents/JVT-Technologies/00-admin/client-registry.csv")
VOICE_AGENT_ROOT = REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "jvt-inbound-voice-agent"
VOICE_AGENT_DATA_ROOT = VOICE_AGENT_ROOT / "data"
DEBIAN_OPS_STATUS_COMMAND = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=8",
    "macmini-i7-debian",
    "~/JVT-Ops/scripts/jvt_status.sh",
]
DEBIAN_BACKUP_LOG_COMMAND = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=8",
    "macmini-i7-debian",
    "tail -80 ~/JVT-Ops/logs/backup.log 2>/dev/null || true",
]
STATUS_LABELS = ("draft", "review", "approved", "sent", "replied")
DECISION_LABELS = ("pending", "approved", "rejected", "executed")

FAST_MODEL_PATH = Path("/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--Qwen2.5-3B-Instruct-4bit")
STRONG_MODEL_PATH = Path("/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--Qwen2.5-7B-Instruct-4bit")
REVIEWER_MODEL_PATH = Path("/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--gpt-oss-20b-MXFP4-Q4")

app = FastAPI(title="JVT Control Panel", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=str(STATIC_ROOT)), name="assets")


class DecisionCreateRequest(BaseModel):
    category: str
    title: str
    recommended_action: str
    context: str = ""
    risk: Literal["low", "medium", "high"] = "medium"
    options: list[str] = Field(default_factory=list)


class DecisionTransitionRequest(BaseModel):
    state: Literal["approved", "rejected", "executed"]
    note: str = ""


class ModelPromptRequest(BaseModel):
    prompt: str
    profile: Literal["fast", "strong", "reviewer"] = "fast"
    include_status_context: bool = True
    max_tokens: int = Field(default=260, ge=64, le=600)


class OutreachTransitionRequest(BaseModel):
    target_state: Literal["draft", "review", "approved"]


class OutreachSendRequest(BaseModel):
    stems: list[str] = Field(default_factory=list)
    confirmed: bool = False


class OutreachWavePrepareRequest(BaseModel):
    packet_date: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=25)


class OutreachWaveSendRequest(BaseModel):
    confirmed: bool = False


class InboxTransitionRequest(BaseModel):
    target_state: Literal["new", "reviewed", "closed"]


_MODEL_LOCK = Lock()
_ACTIVE_MODEL: dict[str, object] = {}
SEND_SCRIPT = REPO_ROOT / "outreach" / "tools" / "send_approved.py"
GENERATE_DAILY_WAVE_SCRIPT = REPO_ROOT / "outreach" / "tools" / "generate_daily_wave.py"


def count_json_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len([path for path in directory.glob("*.json") if path.is_file()])


def count_json_files_recursive(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len([path for path in directory.rglob("*.json") if path.is_file()])


def json_stems(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.json") if path.is_file())


def lead_counts() -> dict[str, int]:
    if not LEAD_DB.exists():
        return {}
    conn = sqlite3.connect(LEAD_DB)
    rows = conn.execute("SELECT outreach_status, COUNT(*) FROM leads GROUP BY outreach_status").fetchall()
    conn.close()
    return {status or "unknown": count for status, count in rows}


def total_leads(lead_status_counts: dict[str, int] | None = None) -> int:
    counts = lead_status_counts or lead_counts()
    return sum(int(count) for count in counts.values())


def recent_leads(limit: int = 10) -> list[dict[str, object]]:
    if not LEAD_DB.exists():
        return []
    conn = sqlite3.connect(LEAD_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, company_name, city_state, practice_area, public_email, fit_score, outreach_status, follow_up_status, last_touched_date
        FROM leads
        ORDER BY fit_score DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def recent_packets(directory: Path, limit: int = 8) -> list[dict[str, object]]:
    if not directory.exists():
        return []
    packets: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["stem"] = path.stem
        payload["path"] = str(path)
        packets.append(payload)
    return packets


def queue_bundle_paths(queue_label: str, stem: str) -> list[Path]:
    directory = OUTREACH_QUEUE / queue_label
    return sorted(path for path in directory.glob(f"{stem}.*") if path.is_file())


def update_metadata_paths(data: dict[str, object], target_dir: Path, stem: str) -> dict[str, object]:
    key_to_suffix = {
        "review_path": ".md",
        "text_path": ".txt",
        "html_path": ".html",
    }
    for key, suffix in key_to_suffix.items():
        if key in data:
            data[key] = str(target_dir / f"{stem}{suffix}")
    return data


def update_review_markdown(path: Path, target_status: str) -> None:
    if not path.exists() or path.suffix != ".md":
        return
    content = path.read_text(encoding="utf-8")
    updated = re.sub(r"^status:\s+\w+\s*$", f"status: {target_status}", content, flags=re.MULTILINE)
    path.write_text(updated, encoding="utf-8")


def move_outreach_packet(source: str, target: str, stem: str) -> dict[str, object]:
    if source not in STATUS_LABELS or target not in STATUS_LABELS:
        raise HTTPException(status_code=400, detail="Invalid outreach queue transition")
    if source == target:
        raise HTTPException(status_code=400, detail="Source and target queues must differ")

    paths = queue_bundle_paths(source, stem)
    if not paths:
        raise HTTPException(status_code=404, detail=f"Outreach packet not found: {source}/{stem}")

    target_dir = OUTREACH_QUEUE / target
    target_dir.mkdir(parents=True, exist_ok=True)

    for path in paths:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            data["status"] = target
            data = update_metadata_paths(data, target_dir, stem)
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        elif path.suffix == ".md":
            update_review_markdown(path, target)

    moved_files: list[str] = []
    for path in paths:
        destination = target_dir / path.name
        path.rename(destination)
        moved_files.append(str(destination))

    return {
        "stem": stem,
        "from_state": source,
        "to_state": target,
        "moved_files": moved_files,
    }


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value, posix=True)
        except ValueError:
            parsed = [value.strip("\"'")]
        values[key] = parsed[0] if parsed else ""
    return values


def outreach_subprocess_env() -> dict[str, str]:
    return {
        **os.environ,
        **load_env_file(OUTREACH_ENV_FILE),
    }


def send_outreach_packets(stems: list[str], confirmed: bool) -> dict[str, object]:
    unique_stems = list(dict.fromkeys(stems))
    if not unique_stems:
        raise HTTPException(status_code=400, detail="Provide at least one approved packet to send")
    if not confirmed:
        raise HTTPException(status_code=400, detail="Send confirmation required")

    outbound_env = outreach_subprocess_env()
    max_per_run = outbound_env.get("JVT_PANEL_SEND_MAX_PER_RUN", "20")
    daily_limit = outbound_env.get("JVT_PANEL_SEND_DAILY_LIMIT", "20")
    delay_seconds = outbound_env.get(
        "JVT_PANEL_SEND_DELAY_SECONDS",
        outbound_env.get("JVT_SEND_DELAY_SECONDS", "5"),
    )

    command = ["python3", str(SEND_SCRIPT)]
    for stem in unique_stems:
        command.extend(["--stem", stem])
    command.extend([
        "--max-per-run",
        max_per_run,
        "--daily-limit",
        daily_limit,
        "--delay-seconds",
        delay_seconds,
        "--send",
    ])

    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=outbound_env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Send failed"
        raise HTTPException(status_code=500, detail=detail)

    events: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {
        "sent_count": len(events),
        "events": events,
    }


def validate_wave_stem(wave_stem: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+", wave_stem):
        raise HTTPException(status_code=400, detail="Invalid outreach wave identifier")
    return wave_stem


def flatten_wave_stems(payload: dict[str, object]) -> list[str]:
    stems: list[str] = []
    for window in payload.get("send_windows", []):
        if not isinstance(window, dict):
            continue
        for stem in window.get("stems", []):
            if isinstance(stem, str) and stem not in stems:
                stems.append(stem)
    return stems


def packet_queue_state(stem: str) -> str:
    for label in STATUS_LABELS:
        if (OUTREACH_QUEUE / label / f"{stem}.json").exists():
            return label
    return "missing"


def packet_summary(stem: str) -> dict[str, object]:
    queue = packet_queue_state(stem)
    summary: dict[str, object] = {
        "stem": stem,
        "queue": queue,
    }
    if queue == "missing":
        return summary

    metadata_path = OUTREACH_QUEUE / queue / f"{stem}.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return summary

    summary.update({
        "company_name": metadata.get("company_name"),
        "recipient_email": metadata.get("recipient_email"),
        "subject": metadata.get("subject"),
        "lead_id": metadata.get("lead_id"),
        "generated_at": metadata.get("generated_at"),
        "sent_at": metadata.get("sent_at"),
    })
    return summary


def load_wave_schedule(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse wave schedule: {path.name}") from exc

    stems = flatten_wave_stems(payload)
    packets = [packet_summary(stem) for stem in stems]
    queue_counts = {label: 0 for label in (*STATUS_LABELS, "missing")}
    for packet in packets:
        queue_counts[str(packet.get("queue") or "missing")] += 1

    wave_stem = path.stem
    return {
        "stem": wave_stem,
        "name": payload.get("name") or wave_stem,
        "status": payload.get("status") or "unknown",
        "scheduled_date": payload.get("scheduled_date"),
        "timezone": payload.get("timezone") or "America/New_York",
        "generated_at": payload.get("generated_at"),
        "send_windows": payload.get("send_windows") or [],
        "selected_leads": payload.get("selected_leads") or [],
        "guardrails": payload.get("guardrails") or [],
        "total_packets": len(stems),
        "packet_counts": queue_counts,
        "packets": packets,
        "paths": {
            "json": str(path),
            "markdown": str(path.with_suffix(".md")),
            "send_script": str(OUTREACH_SCHEDULES / f"send-{wave_stem}.sh"),
        },
    }


def list_outreach_waves(limit: int = 8) -> list[dict[str, object]]:
    if not OUTREACH_SCHEDULES.exists():
        return []
    # Auto-review reports are schedule-adjacent JSON files, not sendable waves.
    paths = sorted(
        (path for path in OUTREACH_SCHEDULES.glob("*.json") if not path.stem.endswith("-auto-review")),
        key=lambda item: (item.name[:10], item.stat().st_mtime),
        reverse=True,
    )
    return [load_wave_schedule(path) for path in paths[:limit]]


def sent_packet_breakdown() -> dict[str, int]:
    sent_dir = OUTREACH_QUEUE / "sent"
    counts = {
        "total": count_json_files(sent_dir),
        "prospect": 0,
        "internal": 0,
    }
    if not sent_dir.exists():
        return counts

    internal_recipients = {
        "chandruvasu@icloud.com",
        "chandruv@icloud.com",
        "chandru@jvt-technologies.com",
        "chandruv@jvt-technologies.com",
    }
    for path in sent_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        recipient = str(payload.get("recipient_email") or "").strip().lower()
        company_name = str(payload.get("company_name") or "").strip().lower()
        is_internal = (
            not recipient
            or recipient in internal_recipients
            or recipient.endswith("@jvt-technologies.com")
            or "jvt technologies" in company_name
            or "test" in company_name
        )
        if is_internal:
            counts["internal"] += 1
        else:
            counts["prospect"] += 1
    return counts


def current_wave_summary() -> dict[str, object]:
    waves = list_outreach_waves(limit=1)
    if not waves:
        return {
            "stem": "",
            "scheduled_date": "",
            "status": "none",
            "total_packets": 0,
            "packet_counts": {label: 0 for label in (*STATUS_LABELS, "missing")},
        }
    wave = waves[0]
    return {
        "stem": wave.get("stem") or "",
        "scheduled_date": wave.get("scheduled_date") or "",
        "status": wave.get("status") or "unknown",
        "total_packets": int(wave.get("total_packets") or 0),
        "packet_counts": wave.get("packet_counts") or {label: 0 for label in (*STATUS_LABELS, "missing")},
    }


def approved_backlog_summary(limit: int = 12) -> dict[str, object]:
    approved_dir = OUTREACH_QUEUE / "approved"
    packets = recent_packets(approved_dir, limit=limit)
    return {
        "count": count_json_files(approved_dir),
        "packets": [
            {
                "stem": str(packet.get("stem") or ""),
                "company_name": packet.get("company_name"),
                "recipient_email": packet.get("recipient_email"),
                "subject": packet.get("subject"),
                "generated_at": packet.get("generated_at"),
            }
            for packet in packets
        ],
    }


def prepare_daily_wave(request: OutreachWavePrepareRequest) -> dict[str, object]:
    packet_date = request.packet_date or datetime.now().date().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", packet_date):
        raise HTTPException(status_code=400, detail="packet_date must use YYYY-MM-DD")

    command = [
        "python3",
        str(GENERATE_DAILY_WAVE_SCRIPT),
        "--root",
        str(REPO_ROOT),
        "--packet-date",
        packet_date,
        "--limit",
        str(request.limit),
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
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Daily wave prep failed"
        raise HTTPException(status_code=500, detail=detail)

    schedule_path = OUTREACH_SCHEDULES / f"{packet_date}-daily-wave.json"
    if not schedule_path.exists():
        raise HTTPException(status_code=500, detail=f"Daily wave schedule was not created: {schedule_path.name}")

    return {
        "prepared": True,
        "stdout": result.stdout.strip(),
        "wave": load_wave_schedule(schedule_path),
    }


def approve_outreach_wave(wave_stem: str) -> dict[str, object]:
    schedule_path = OUTREACH_SCHEDULES / f"{validate_wave_stem(wave_stem)}.json"
    if not schedule_path.exists():
        raise HTTPException(status_code=404, detail=f"Outreach wave not found: {wave_stem}")

    wave = load_wave_schedule(schedule_path)
    moved: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for stem in (packet["stem"] for packet in wave["packets"]):
        state = packet_queue_state(str(stem))
        if state == "review":
            moved.append(move_outreach_packet("review", "approved", str(stem)))
        else:
            skipped.append({"stem": stem, "state": state})

    return {
        "wave_stem": wave_stem,
        "moved_count": len(moved),
        "skipped": skipped,
        "moved": moved,
        "wave": load_wave_schedule(schedule_path),
    }


def send_outreach_wave(wave_stem: str, confirmed: bool) -> dict[str, object]:
    schedule_path = OUTREACH_SCHEDULES / f"{validate_wave_stem(wave_stem)}.json"
    if not schedule_path.exists():
        raise HTTPException(status_code=404, detail=f"Outreach wave not found: {wave_stem}")

    wave = load_wave_schedule(schedule_path)
    approved_stems = [
        str(packet["stem"])
        for packet in wave["packets"]
        if packet.get("queue") == "approved"
    ]
    if not approved_stems:
        raise HTTPException(status_code=400, detail="No approved packets found in this wave")

    result = send_outreach_packets(approved_stems, confirmed)
    return {
        "wave_stem": wave_stem,
        "requested_count": len(approved_stems),
        **result,
        "wave": load_wave_schedule(schedule_path),
    }


def packet_detail(queue_label: str, stem: str) -> dict[str, object]:
    if queue_label not in STATUS_LABELS:
        raise HTTPException(status_code=404, detail=f"Unknown outreach queue: {queue_label}")

    directory = OUTREACH_QUEUE / queue_label
    metadata_path = directory / f"{stem}.json"
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail=f"Outreach packet not found: {queue_label}/{stem}")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse packet metadata: {stem}") from exc

    text_path = directory / f"{stem}.txt"
    html_path = directory / f"{stem}.html"
    review_path = directory / f"{stem}.md"

    return {
        "queue": queue_label,
        "stem": stem,
        "metadata": metadata,
        "text_body": text_path.read_text(encoding="utf-8").strip() if text_path.exists() else "",
        "html_body": html_path.read_text(encoding="utf-8").strip() if html_path.exists() else "",
        "review_body": review_path.read_text(encoding="utf-8").strip() if review_path.exists() else "",
    }


PROMO_MARKERS = (
    "unsubscribe",
    "view this email as a web page",
    "special offer",
    "% off",
    "limited time",
    "newsletter",
    "sale",
    "order delivered",
    "survey",
    "please share your thoughts",
)
PROMO_DOMAINS = (
    "mailchimp",
    "sfmc",
    "messagegears",
    "constantcontact",
    "hubspot",
    "sailthru",
    "beehiiv",
    "newsletter",
    "service.alibaba.com",
    "mg.homedepot.com",
    "qemailserver.com",
)
SYSTEM_MARKERS = (
    "dmarc",
    "aggregate report",
    "report domain",
    "submitter:",
    "verification",
    "verify your email",
    "security",
    "oauth",
    "password",
    "receipt",
    "invoice",
    "bank",
    "card",
    "venmo",
    "github",
    "postman",
    "application was approved",
    "account application",
    "touch id",
    "face id",
    "run failed",
)


def effective_inbox_payload(payload: dict[str, object], path: Path) -> dict[str, object]:
    item = dict(payload)
    item["path"] = str(path)
    item["stem"] = path.stem

    subject = str(item.get("subject") or "")
    snippet = str(item.get("snippet") or "")
    sender = str(item.get("from") or "")
    recipient = str(item.get("to") or "")
    sender_addr = str(item.get("sender_email") or parseaddr(sender)[1]).lower().strip()
    recipient_addr = str(item.get("recipient_email") or parseaddr(recipient)[1] or recipient).lower().strip()
    sender_domain = str(item.get("sender_domain") or (sender_addr.split("@", 1)[1] if "@" in sender_addr else "")).lower()
    subject_l = subject.lower()
    snippet_l = snippet.lower()
    existing_bucket = str(item.get("triage_bucket") or "unknown")

    if recipient_addr.endswith("@jvt-technologies.com"):
        if sender_addr.endswith("@jvt-technologies.com"):
            item["triage_bucket"] = "internal-test"
            item["triage_priority"] = "low"
            item["triage_action"] = "ignore"
        elif any(token in sender_addr for token in ("noreply", "no-reply", "do-not-reply")):
            item["triage_bucket"] = "system"
            item["triage_priority"] = "low"
            item["triage_action"] = "defer"
        else:
            item["triage_bucket"] = "direct"
            item["triage_priority"] = "high"
            item["triage_action"] = "review"
        return item

    if existing_bucket == "review":
        if any(marker in subject_l or marker in snippet_l for marker in PROMO_MARKERS) or any(domain in sender_domain for domain in PROMO_DOMAINS):
            item["triage_bucket"] = "promotional"
            item["triage_priority"] = "low"
            item["triage_action"] = "ignore"
            item["triage_reason"] = "effective_promotional_reclass"
        elif any(marker in subject_l or marker in sender_domain for marker in SYSTEM_MARKERS):
            item["triage_bucket"] = "system"
            item["triage_priority"] = "low"
            item["triage_action"] = "defer"
            item["triage_reason"] = "effective_system_reclass"
        else:
            item["triage_bucket"] = "personal"
            item["triage_priority"] = "low"
            item["triage_action"] = "defer"
            item["triage_reason"] = "effective_personal_reclass"
    return item


def recent_inbox_messages(limit: int = 8) -> list[dict[str, object]]:
    candidates: list[Path] = []
    for label in ("new", "reviewed", "closed"):
        directory = INBOX_ROOT / label
        if directory.exists():
            candidates.extend(path for path in directory.rglob("*.json") if path.is_file())

    messages: list[dict[str, object]] = []
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        item = effective_inbox_payload(payload, path)
        item["_mtime"] = path.stat().st_mtime
        messages.append(item)

    priority_rank = {
        "direct": 0,
        "review": 1,
        "system": 2,
        "personal": 3,
        "internal-test": 4,
        "promotional": 5,
    }
    status_rank = {
        "new": 0,
        "reviewed": 1,
        "closed": 2,
    }
    messages.sort(
        key=lambda item: (
            0
            if item.get("status") == "new"
            and str(item.get("triage_bucket") or "") in {"direct", "review"}
            else 1,
            status_rank.get(str(item.get("status") or "new"), 2),
            priority_rank.get(str(item.get("triage_bucket") or "unknown"), 5),
            -float(item.get("_mtime") or 0),
        )
    )
    for item in messages:
        item.pop("_mtime", None)
    return messages[:limit]


def inbox_bucket_counts(labels: tuple[str, ...] = ("new",)) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for label in labels:
        directory = INBOX_ROOT / label
        if not directory.exists():
            continue
        for path in directory.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                bucket = "parse_error"
            else:
                bucket = str(effective_inbox_payload(payload, path).get("triage_bucket") or "unknown")
            buckets[bucket] = buckets.get(bucket, 0) + 1
    return buckets


def find_inbox_json(stem: str) -> Path:
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]", "", stem)
    if not safe_stem or safe_stem != stem:
        raise HTTPException(status_code=400, detail="Invalid inbox message id")
    matches = [path for path in INBOX_ROOT.rglob(f"{safe_stem}.json") if path.is_file()]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Inbox message not found: {stem}")
    return sorted(matches, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def move_inbox_message(stem: str, target_state: str) -> dict[str, object]:
    if target_state not in {"new", "reviewed", "closed"}:
        raise HTTPException(status_code=400, detail=f"Unknown inbox target state: {target_state}")
    source_json = find_inbox_json(stem)
    try:
        payload = json.loads(source_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse inbox message: {stem}") from exc

    captured_day = str(payload.get("captured_at") or "")[:10]
    day = captured_day if re.match(r"^\d{4}-\d{2}-\d{2}$", captured_day) else source_json.parent.name
    target_dir = INBOX_ROOT / target_state / day
    target_dir.mkdir(parents=True, exist_ok=True)

    moved: dict[str, str] = {}
    for suffix in (".json", ".eml"):
        source = source_json.with_suffix(suffix)
        if not source.exists():
            continue
        target = target_dir / source.name
        if source.resolve() == target.resolve():
            moved[suffix.lstrip(".")] = str(target)
            continue
        if target.exists():
            target = target_dir / f"{source.stem}-{datetime.now(timezone.utc).strftime('%H%M%S')}{suffix}"
        source.rename(target)
        moved[suffix.lstrip(".")] = str(target)

    payload["status"] = target_state
    target_json = Path(moved.get("json", str(target_dir / source_json.name)))
    target_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"stem": stem, "target_state": target_state, "paths": moved, "message": effective_inbox_payload(payload, target_json)}


def list_decisions(state: str) -> list[dict[str, object]]:
    directory = CONTROL_ROOT / state
    if not directory.exists():
        return []
    decisions: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["path"] = str(path)
        decisions.append(payload)
    return decisions


def read_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_status_datetime(value: object) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_compact_utc_timestamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def owned_ops_status() -> dict[str, object]:
    timed_out = False
    try:
        result = subprocess.run(
            DEBIAN_OPS_STATUS_COMMAND,
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        result = subprocess.CompletedProcess(
            DEBIAN_OPS_STATUS_COMMAND,
            124,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr="Debian ops status command timed out.",
        )
    parsed: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        parsed[key.strip()] = value.strip()

    backup_timed_out = False
    try:
        backup_log_result = subprocess.run(
            DEBIAN_BACKUP_LOG_COMMAND,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        backup_timed_out = True
        backup_log_result = subprocess.CompletedProcess(
            DEBIAN_BACKUP_LOG_COMMAND,
            124,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr="Debian backup log command timed out.",
        )
    backup_lines = backup_log_result.stdout.strip().splitlines()
    last_backup_line = backup_lines[-1] if backup_lines else ""
    last_backup_timestamp = ""
    last_backup_age_seconds = None
    matches = re.findall(r"backup_complete timestamp=(\d{8}T\d{6}Z)", backup_log_result.stdout)
    if matches:
        last_backup_timestamp = sorted(matches)[-1]
        parsed_backup_at = parse_compact_utc_timestamp(last_backup_timestamp)
        if parsed_backup_at:
            last_backup_age_seconds = max(0, int((datetime.now(timezone.utc) - parsed_backup_at).total_seconds()))

    findings: list[str] = []
    debian_reachable = result.returncode == 0
    if timed_out:
        findings.append("Debian ops status command timed out.")
    if not debian_reachable:
        findings.append("Debian ops status command failed.")
    if backup_timed_out:
        findings.append("Debian backup log command timed out.")
    if parsed.get("cloudflare_tunnel") != "running":
        findings.append("Cloudflare tunnel is not reporting running from Debian status.")
    if "status\":\"ok\"" not in parsed.get("voice_public", ""):
        findings.append("Public voice health did not return ok.")
    if "status\":\"ok\"" not in parsed.get("voice_m4", ""):
        findings.append("M4 local voice health did not return ok.")
    if parsed.get("debian_latest_backup") in {"", "missing", None}:
        findings.append("Debian local JVT backup is missing.")
    if last_backup_age_seconds is None:
        findings.append("Could not read latest Debian backup timestamp.")
    elif last_backup_age_seconds > 36 * 60 * 60:
        findings.append("Latest Debian backup is older than 36 hours.")
    if "AC attached" not in parsed.get("m4_ups", ""):
        findings.append("M4 UPS is not reporting AC attached.")

    return {
        "ok": debian_reachable and not findings,
        "debian_reachable": debian_reachable,
        "generated_at": parsed.get("jvt_status generated_at", ""),
        "debian_disk": parsed.get("debian_disk", "unknown"),
        "debian_load": parsed.get("debian_load", "unknown"),
        "debian_mem": parsed.get("debian_mem", "unknown"),
        "voice_public": parsed.get("voice_public", ""),
        "voice_m4": parsed.get("voice_m4", ""),
        "cloudflare_tunnel": parsed.get("cloudflare_tunnel", "unknown"),
        "m4_ups": parsed.get("m4_ups", "unknown"),
        "debian_latest_backup": parsed.get("debian_latest_backup", "unknown"),
        "last_backup_line": last_backup_line,
        "last_backup_timestamp": last_backup_timestamp,
        "last_backup_age_seconds": last_backup_age_seconds,
        "backup_target": "Debian local only",
        "second_backup_target": "Paused until owned hardware is approved",
        "findings": findings,
    }


def watchdog_status_summary() -> dict[str, object]:
    payload = read_json_file(WATCHDOG_STATE_PATH)
    if not payload:
        return {
            "ok": False,
            "overall_ok": False,
            "generated_at": "",
            "state_age_seconds": None,
            "finding_count": 1,
            "findings": ["No watchdog state file found."],
        }

    generated_at = parse_status_datetime(payload.get("generated_at"))
    age_seconds = (
        max(0, int((datetime.now(timezone.utc) - generated_at).total_seconds()))
        if generated_at
        else None
    )
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    return {
        "ok": bool(payload.get("overall_ok")) and not findings,
        "overall_ok": bool(payload.get("overall_ok")),
        "generated_at": payload.get("generated_at") or "",
        "state_age_seconds": age_seconds,
        "finding_count": len(findings),
        "findings": findings,
        "http": payload.get("http") or {},
        "launchd": payload.get("launchd") or {},
        "service_board": payload.get("service_board") or {},
        "trader": payload.get("trader") or {},
        "queue_counts": payload.get("queue_counts") or {},
        "inbox_counts": payload.get("inbox_counts") or {},
    }


def payload_age_seconds(payload: dict[str, object], *keys: str) -> int | None:
    for key in keys:
        parsed = parse_status_datetime(payload.get(key))
        if parsed:
            return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    return None


def tcp_pressure_summary() -> dict[str, object]:
    payload = read_json_file(TCP_PRESSURE_STATE_PATH)
    if not payload:
        return {
            "ok": False,
            "severity": "missing",
            "state_age_seconds": None,
            "finding": "No TCP pressure state file found.",
            "path": str(TCP_PRESSURE_STATE_PATH),
        }

    tcp = payload.get("tcp") if isinstance(payload.get("tcp"), dict) else {}
    states = tcp.get("states") if isinstance(tcp.get("states"), dict) else {}
    mbufs = payload.get("mbufs") if isinstance(payload.get("mbufs"), dict) else {}
    loopback_checks = payload.get("loopback_checks") if isinstance(payload.get("loopback_checks"), dict) else {}
    top_processes = tcp.get("top_processes") if isinstance(tcp.get("top_processes"), list) else []
    severity = str(payload.get("severity") or "unknown")
    return {
        "ok": severity not in {"critical", "missing"},
        "severity": severity,
        "generated_at": payload.get("checked_at") or "",
        "state_age_seconds": payload_age_seconds(payload, "checked_at"),
        "tcp_tuning_ok": bool((payload.get("tcp_tuning") or {}).get("ok")) if isinstance(payload.get("tcp_tuning"), dict) else None,
        "loopback_ok": all(bool(item.get("ok")) for item in loopback_checks.values()) if loopback_checks else None,
        "time_wait": int(states.get("TIME_WAIT") or 0),
        "syn_sent": int(states.get("SYN_SENT") or 0),
        "mbuf_network_percent": mbufs.get("network_percent_in_use"),
        "memory_denied_delta": mbufs.get("memory_denied_delta"),
        "memory_denied_requests": mbufs.get("memory_denied_requests"),
        "top_processes": top_processes[:6],
        "path": str(TCP_PRESSURE_STATE_PATH),
    }


def auto_send_summary() -> dict[str, object]:
    payload = read_json_file(AUTO_SEND_STATE_PATH)
    if not payload:
        return {
            "ok": False,
            "status": "missing",
            "state_age_seconds": None,
            "path": str(AUTO_SEND_STATE_PATH),
        }

    send_result = payload.get("send_result") if isinstance(payload.get("send_result"), dict) else {}
    sent_after = payload.get("sent_after") if isinstance(payload.get("sent_after"), dict) else {}
    selected_stems = payload.get("selected_stems") if isinstance(payload.get("selected_stems"), list) else []
    dynamic_caps = payload.get("dynamic_caps") if isinstance(payload.get("dynamic_caps"), dict) else {}
    effective_caps = dynamic_caps.get("effective") if isinstance(dynamic_caps.get("effective"), dict) else {}
    base_caps = dynamic_caps.get("base") if isinstance(dynamic_caps.get("base"), dict) else payload.get("base_caps") or {}
    remaining_caps = dynamic_caps.get("remaining") if isinstance(dynamic_caps.get("remaining"), dict) else {}
    return {
        "ok": str(payload.get("status") or "") in {"sent", "idle", "dry-run"},
        "status": payload.get("status") or "unknown",
        "mode": payload.get("mode") or "unknown",
        "generated_at": payload.get("generated_at") or "",
        "state_age_seconds": payload_age_seconds(payload, "generated_at"),
        "auto_send_enabled": bool(payload.get("auto_send_enabled")),
        "requires_operator_confirmation": bool(payload.get("requires_operator_confirmation")),
        "max_per_run": payload.get("max_per_run"),
        "daily_total_cap": payload.get("daily_total_cap"),
        "daily_initial_cap": payload.get("daily_initial_cap") or effective_caps.get("initial"),
        "daily_followup_cap": payload.get("daily_followup_cap") or effective_caps.get("followup"),
        "base_caps": base_caps,
        "effective_caps": effective_caps,
        "remaining_caps": remaining_caps,
        "cap_adjustments": dynamic_caps.get("adjustments") or [],
        "selected_count": len(selected_stems),
        "selected_stems": selected_stems[:12],
        "sent_count": send_result.get("sent_count") or 0,
        "sent_today_total": sent_after.get("total") or 0,
        "sent_today_initial": sent_after.get("initial") or 0,
        "sent_today_followup": sent_after.get("followup") or 0,
        "block_reason": payload.get("block_reason") or "",
        "guards": payload.get("guards") or {},
        "path": str(AUTO_SEND_STATE_PATH),
    }


def operator_alerts_summary() -> dict[str, object]:
    payload = read_json_file(OPERATOR_ALERTS_STATE_PATH)
    if not payload:
        return {
            "ok": True,
            "active_count": 0,
            "new_count": 0,
            "alerts": [],
            "path": str(OPERATOR_ALERTS_STATE_PATH),
        }
    alerts = payload.get("alerts") if isinstance(payload.get("alerts"), list) else []
    return {
        "ok": True,
        "generated_at": payload.get("generated_at") or "",
        "state_age_seconds": payload_age_seconds(payload, "generated_at"),
        "active_count": payload.get("active_count") or len(alerts),
        "new_count": payload.get("new_count") or 0,
        "alerts": alerts[:5],
        "path": str(OPERATOR_ALERTS_STATE_PATH),
    }


def agent_interop_summary() -> dict[str, object]:
    payload = read_json_file(AGENT_INTEROP_STATE_PATH)
    if not payload:
        return {
            "ok": False,
            "generated_at": "",
            "state_age_seconds": None,
            "finding_count": 1,
            "findings": [{"level": "warning", "message": "No agent interop state file found."}],
            "summary": {},
            "handoffs": [],
            "launchd": {},
            "endpoints": {},
            "path": str(AGENT_INTEROP_STATE_PATH),
        }

    generated_at = parse_status_datetime(payload.get("generated_at"))
    age_seconds = (
        max(0, int((datetime.now(timezone.utc) - generated_at).total_seconds()))
        if generated_at
        else None
    )
    payload["state_age_seconds"] = age_seconds
    payload["path"] = str(AGENT_INTEROP_STATE_PATH)
    return payload


def state_file_summary(path: Path, *, ok_when_missing: bool = False) -> dict[str, object]:
    payload = read_json_file(path)
    if not payload:
        return {
            "ok": ok_when_missing,
            "status": "missing",
            "generated_at": "",
            "state_age_seconds": None,
            "path": str(path),
        }
    payload["path"] = str(path)
    payload["state_age_seconds"] = payload_age_seconds(payload, "generated_at", "checked_at")
    return payload


def business_readiness_summary() -> dict[str, object]:
    opportunity = state_file_summary(OPPORTUNITY_MANAGER_STATE_PATH)
    voice_readiness = state_file_summary(VOICE_READINESS_STATE_PATH)
    paper_trader = state_file_summary(PAPER_TRADER_HEALTH_STATE_PATH)
    source_hygiene = state_file_summary(SOURCE_HYGIENE_STATE_PATH)
    system_resources = state_file_summary(SYSTEM_RESOURCES_STATE_PATH)
    findings: list[str] = []
    if int(opportunity.get("response_needed_count") or 0):
        findings.append(f"{opportunity.get('response_needed_count')} active opportunity response(s) need review.")
    if not bool(voice_readiness.get("demo_ready")):
        findings.append("Voice readiness is not demo-ready.")
    if paper_trader.get("findings"):
        findings.extend(str(item) for item in (paper_trader.get("findings") or [])[:3])
    if int(source_hygiene.get("status_count") or 0) > 250:
        findings.append(f"Source tree is very dirty: {source_hygiene.get('status_count')} entries.")
    if system_resources.get("findings"):
        findings.extend(str(item) for item in (system_resources.get("findings") or [])[:3])
    return {
        "ok": not findings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings": findings,
        "opportunity_manager": opportunity,
        "voice_readiness": voice_readiness,
        "paper_trader": paper_trader,
        "source_hygiene": source_hygiene,
        "system_resources": system_resources,
        "guardrail": "Readiness visibility only. This panel does not send, spend, trade, mine, stake, post, or commit.",
    }


def orchestrator_summary() -> dict[str, object]:
    payload = read_json_file(ORCHESTRATOR_STATE_PATH)
    if not payload:
        return {
            "ok": False,
            "status": "missing",
            "generated_at": "",
            "state_age_seconds": None,
            "policy": {},
            "quotas": {},
            "lanes": [],
            "work_items": [],
            "blockers": [{"title": "No orchestrator state file found."}],
            "path": str(ORCHESTRATOR_STATE_PATH),
            "safety_boundary": "No sends, payments, live trades, external commitments, wallets, mining, staking, or custody workflows are performed by the orchestrator.",
        }

    generated_at = parse_status_datetime(payload.get("generated_at"))
    payload["state_age_seconds"] = (
        max(0, int((datetime.now(timezone.utc) - generated_at).total_seconds()))
        if generated_at
        else None
    )
    payload["checkin"] = growth_checkin_summary()
    payload["path"] = str(ORCHESTRATOR_STATE_PATH)
    return payload


def growth_checkin_summary() -> dict[str, object]:
    payload = read_json_file(GROWTH_CHECKIN_STATE_PATH)
    if not payload:
        return {
            "ok": False,
            "generated_at": "",
            "state_age_seconds": None,
            "safe_action_count": 0,
            "top_work_count": 0,
            "path": str(GROWTH_CHECKIN_STATE_PATH),
        }
    generated_at = parse_status_datetime(payload.get("generated_at"))
    payload["state_age_seconds"] = (
        max(0, int((datetime.now(timezone.utc) - generated_at).total_seconds()))
        if generated_at
        else None
    )
    payload["safe_action_count"] = len(payload.get("safe_actions") or [])
    payload["top_work_count"] = len(payload.get("top_work_items") or [])
    payload["path"] = str(GROWTH_CHECKIN_STATE_PATH)
    return payload


def latest_followup_report() -> dict[str, object]:
    if not FOLLOWUP_REPORT_DIR.exists():
        return {}
    reports = sorted(FOLLOWUP_REPORT_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return read_json_file(reports[0]) if reports else {}


def is_prospect_outreach(payload: dict[str, object]) -> bool:
    recipient = str(payload.get("recipient_email") or "").strip().lower()
    company_name = str(payload.get("company_name") or "").strip().lower()
    internal_recipients = {
        "chandruvasu@icloud.com",
        "chandruv@icloud.com",
        "chandru@jvt-technologies.com",
        "chandruv@jvt-technologies.com",
    }
    return bool(recipient) and not (
        recipient in internal_recipients
        or recipient.endswith("@jvt-technologies.com")
        or "jvt technologies" in company_name
        or company_name == "test"
        or "self-test" in company_name
    )


FOLLOWUP_GENERIC_COMPANY_PATTERNS = (
    re.compile(r"^top\s+", re.IGNORECASE),
    re.compile(r"^cpa\s+firm\b", re.IGNORECASE),
    re.compile(r"\bcpa\s+[a-z ,.-]+accounting\s+firm\b", re.IGNORECASE),
    re.compile(r"^[a-z .'-]+,\s*[A-Z]{2}\s+(accounting|cpa|law|property)\b", re.IGNORECASE),
    re.compile(r"\b(accounting|cpa|law)\s+firm\s+for\b", re.IGNORECASE),
    re.compile(r"\b(home|contact|about|splash)\s+page\b", re.IGNORECASE),
    re.compile(r"\b(best|expert|trusted)\s+(accounting|cpa|law)\b", re.IGNORECASE),
    re.compile(r"\bwebsites?\b", re.IGNORECASE),
    re.compile(r"\boutsourcing\s+services\b", re.IGNORECASE),
)
FOLLOWUP_OFF_TARGET_TERMS = ("outsourcing", "outsourced", "seo", "web design", "software platform", "staffing")
FOLLOWUP_SUSPICIOUS_LOCAL_PARTS = {"seo", "marketing", "webmaster", "noreply", "no-reply", "donotreply", "do-not-reply"}


def passes_followup_quality_gate(payload: dict[str, object]) -> bool:
    recipient = str(payload.get("recipient_email") or "").strip().lower()
    company = str(payload.get("company_name") or "").strip()
    company_lower = company.lower()
    if not company or any(pattern.search(company) for pattern in FOLLOWUP_GENERIC_COMPANY_PATTERNS):
        return False
    if "@" not in recipient or recipient.split("@", 1)[0] in FOLLOWUP_SUSPICIOUS_LOCAL_PARTS:
        return False
    return not any(term in company_lower for term in FOLLOWUP_OFF_TARGET_TERMS)


def follow_up_summary(min_age_days: int = 4, limit: int = 8) -> dict[str, object]:
    sent_dir = OUTREACH_QUEUE / "sent"
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
    existing_followups: set[tuple[str, str]] = set()
    staged_counts = {label: 0 for label in STATUS_LABELS}
    sent_followups = 0

    for label in STATUS_LABELS:
        directory = OUTREACH_QUEUE / label
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            payload = read_json_file(path)
            parent = str(payload.get("follow_up_parent_stem") or "")
            stage = str(payload.get("follow_up_stage") or "")
            if not parent or not stage:
                continue
            existing_followups.add((parent, stage))
            staged_counts[label] += 1
            if label == "sent":
                sent_followups += 1

    eligible: list[dict[str, object]] = []
    eligible_count = 0
    recent_sent = 0
    now = datetime.now(timezone.utc)
    if sent_dir.exists():
        for path in sorted(sent_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
            payload = read_json_file(path)
            if not is_prospect_outreach(payload) or payload.get("follow_up_stage"):
                continue
            if not passes_followup_quality_gate(payload):
                continue
            sent_at = parse_status_datetime(payload.get("sent_at"))
            if sent_at and now - sent_at <= timedelta(hours=24):
                recent_sent += 1
            if not sent_at or sent_at > cutoff:
                continue
            if (path.stem, "1") in existing_followups:
                continue
            eligible_count += 1
            if len(eligible) < limit:
                eligible.append({
                    "stem": path.stem,
                    "company_name": payload.get("company_name"),
                    "recipient_email": payload.get("recipient_email"),
                    "sent_at": payload.get("sent_at"),
                    "subject": payload.get("subject"),
                })

    report = latest_followup_report()
    return {
        "min_age_days": min_age_days,
        "eligible_count": eligible_count,
        "eligible_sample": eligible,
        "draft_queue": staged_counts.get("draft", 0),
        "review_queue": staged_counts.get("review", 0),
        "approved_queue": staged_counts.get("approved", 0),
        "sent_followups": sent_followups,
        "prospect_sent_last_24h": recent_sent,
        "latest_report_generated_at": report.get("generated_at") or "",
        "latest_report_written_count": report.get("written_count") or 0,
    }


def client_registry_count() -> int:
    if not CLIENT_REGISTRY.exists():
        return 0
    try:
        with CLIENT_REGISTRY.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return sum(1 for row in reader if row.get("client_slug") or row.get("client_name"))
    except PermissionError:
        return 0


def recent_voice_intake(limit: int = 5) -> list[dict[str, object]]:
    intake_root = VOICE_AGENT_DATA_ROOT / "intake"
    if not intake_root.exists():
        return []
    items: list[dict[str, object]] = []
    for path in sorted(intake_root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["stem"] = path.stem
        payload["path"] = str(path)
        items.append(payload)
    return items


def voice_agent_status(limit: int = 5) -> dict[str, object]:
    env_path = VOICE_AGENT_ROOT / ".env.local"
    run_script = VOICE_AGENT_ROOT / "tools" / "run_voice_agent.sh"
    call_root = VOICE_AGENT_DATA_ROOT / "calls"
    intake_root = VOICE_AGENT_DATA_ROOT / "intake"
    env_values = load_env_file(env_path)
    has_openai_key = bool(env_values.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    response_engine = str(env_values.get("JVT_VOICE_RESPONSE_ENGINE") or os.environ.get("JVT_VOICE_RESPONSE_ENGINE") or "local-model-router").strip().lower()
    openai_required = response_engine in {"openai", "openai-realtime"}
    local_audio_bridge_ready = str(env_values.get("JVT_VOICE_LOCAL_AUDIO_BRIDGE_READY", "0")).strip().lower() in {"1", "true", "yes", "on"}
    dry_run = str(env_values.get("JVT_VOICE_DRY_RUN", "1")).strip().lower() in {"1", "true", "yes", "on"}
    public_base_url = env_values.get("JVT_VOICE_PUBLIC_BASE_URL", "")
    phone_provider_configured = str(env_values.get("JVT_VOICE_PHONE_PROVIDER_CONFIGURED", "0")).strip().lower() in {"1", "true", "yes", "on"}
    live_audio_backend_ready = (openai_required and has_openai_key) or (
        response_engine in {"local-audio-bridge", "local-realtime"} and local_audio_bridge_ready
    )
    effective_dry_run = dry_run or (openai_required and not has_openai_key)
    media_stream_url = ""
    if public_base_url.startswith("https://"):
        media_stream_url = f"wss://{public_base_url.removeprefix('https://').rstrip('/')}/twilio/media-stream"
    elif public_base_url.startswith("http://"):
        media_stream_url = f"ws://{public_base_url.removeprefix('http://').rstrip('/')}/twilio/media-stream"
    configured_for_live = live_audio_backend_ready and bool(public_base_url) and not effective_dry_run and phone_provider_configured

    return {
        "status": "live-ready" if configured_for_live else "dry-run",
        "app_exists": VOICE_AGENT_ROOT.exists(),
        "env_exists": env_path.exists(),
        "run_script_exists": run_script.exists(),
        "has_openai_key": has_openai_key,
        "openai_required": openai_required,
        "response_engine": response_engine,
        "local_model_router_url": env_values.get("JVT_MODEL_ROUTER_URL") or "http://127.0.0.1:8760",
        "local_audio_bridge_ready": local_audio_bridge_ready,
        "live_audio_backend_ready": live_audio_backend_ready,
        "dry_run": effective_dry_run,
        "public_base_url": public_base_url,
        "media_stream_url": media_stream_url,
        "phone_provider_configured": phone_provider_configured,
        "live_ready": configured_for_live,
        "live_ready_gates": {
            "openai_api_key": has_openai_key,
            "openai_required": openai_required,
            "local_audio_bridge_ready": local_audio_bridge_ready,
            "live_audio_backend_ready": live_audio_backend_ready,
            "public_https_base_url": bool(public_base_url) and public_base_url.startswith("https://"),
            "media_stream_url": bool(media_stream_url) and media_stream_url.startswith("wss://"),
            "dry_run_disabled": not effective_dry_run,
            "phone_provider_confirmed": phone_provider_configured,
        },
        "local_url": "http://127.0.0.1:8066",
        "twilio_webhook": "/twilio/inbound",
        "call_count": count_json_files(call_root),
        "intake_count": count_json_files(intake_root),
        "recent_intake": recent_voice_intake(limit=limit),
        "next_step": (
            "Ready for a live inbound call test."
            if configured_for_live
            else "Dry-run scaffold is installed. Local model router is the default reasoning path; live phone calls still need an approved local realtime audio bridge and phone provider."
        ),
    }


def revenue_opportunities(limit: int = 5) -> dict[str, object]:
    payload = read_json_file(REVENUE_OPPORTUNITIES_PATH)
    opportunities = payload.get("opportunities", [])
    if not isinstance(opportunities, list):
        opportunities = []
    sources = payload.get("sources", [])
    red_lines = payload.get("red_lines", [])
    return {
        "updated_at": payload.get("updated_at") or "",
        "recommendation": payload.get("recommendation") or "",
        "items": opportunities[:limit],
        "source_count": len(sources) if isinstance(sources, list) else 0,
        "red_lines": red_lines if isinstance(red_lines, list) else [],
        "path": str(REVENUE_OPPORTUNITIES_PATH),
    }


def crypto_lab_status() -> dict[str, object]:
    report = read_json_file(CRYPTO_LAB_REPORT)
    generated_at = parse_status_datetime(report.get("generated_at"))
    age_seconds = (
        max(0, int((datetime.now(timezone.utc) - generated_at).total_seconds()))
        if generated_at
        else None
    )
    proof_of_work = report.get("proof_of_work") if isinstance(report.get("proof_of_work"), list) else []
    proof_of_stake = report.get("proof_of_stake") if isinstance(report.get("proof_of_stake"), list) else []
    compute_market = report.get("compute_market") if isinstance(report.get("compute_market"), list) else []

    def best_monthly(rows: list[object], key: str) -> float:
        values = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                values.append(float(row.get(key) or 0))
            except (TypeError, ValueError):
                continue
        return round(max(values), 2) if values else 0.0

    return {
        "ok": bool(report),
        "root": str(CRYPTO_LAB_ROOT),
        "report_path": str(CRYPTO_LAB_REPORT),
        "html_path": str(CRYPTO_LAB_HTML),
        "html_exists": CRYPTO_LAB_HTML.exists(),
        "script_exists": CRYPTO_LAB_SCRIPT.exists(),
        "config_exists": CRYPTO_LAB_CONFIG.exists(),
        "generated_at": report.get("generated_at") or "",
        "state_age_seconds": age_seconds,
        "verdict": report.get("verdict") or "No crypto lab report has been generated.",
        "electricity_usd_per_kwh": report.get("electricity_usd_per_kwh"),
        "prices_usd": report.get("prices_usd") or {},
        "best_pow_net_monthly_usd": best_monthly(proof_of_work, "net_monthly_usd"),
        "best_staking_monthly_usd": best_monthly(proof_of_stake, "risk_adjusted_monthly_usd"),
        "best_compute_monthly_usd": best_monthly(compute_market, "net_monthly_usd"),
        "proof_of_work": proof_of_work,
        "proof_of_stake": proof_of_stake,
        "compute_market": compute_market,
        "guardrail": "Read-only feasibility only: no wallets, miners, staking keys, fund movement, or custody workflows.",
    }


def run_crypto_lab(offline: bool = False) -> dict[str, object]:
    if not CRYPTO_LAB_SCRIPT.exists():
        raise HTTPException(status_code=404, detail=f"Crypto lab script not found: {CRYPTO_LAB_SCRIPT}")
    command = ["python3", str(CRYPTO_LAB_SCRIPT), "--config", str(CRYPTO_LAB_CONFIG)]
    if offline:
        command.append("--offline")
    result = subprocess.run(
        command,
        cwd=str(CRYPTO_LAB_ROOT),
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Crypto lab refresh failed"
        raise HTTPException(status_code=500, detail=detail)
    return {
        "refreshed": True,
        "stdout": result.stdout.strip(),
        "crypto_lab": crypto_lab_status(),
    }


def load_agents(
    lead_status_counts: dict[str, int] | None = None,
    queue_counts: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    if not AGENT_ROOT.exists():
        return []

    counts = lead_status_counts or lead_counts()
    queues = queue_counts or {label: count_json_files(OUTREACH_QUEUE / label) for label in STATUS_LABELS}
    research_state = read_json_file(RESEARCH_STATE_PATH)
    client_count = client_registry_count()

    items: list[dict[str, object]] = []
    for path in sorted(AGENT_ROOT.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        slug = str(payload.get("slug") or path.stem)
        runtime_status = str(payload.get("status") or "planned")
        summary = ""
        last_run = ""
        metrics: list[dict[str, str]] = []

        if slug == "lead-research":
            runtime_status = "active"
            last_run = str(research_state.get("last_run") or "")
            summary = (
                f"{total_leads(counts)} total leads. Conservative legal and accounting research lanes are active."
            )
            metrics = [
                {"label": "last run", "value": last_run or "unknown"},
                {"label": "total leads", "value": str(total_leads(counts))},
            ]
        elif slug == "outreach":
            runtime_status = "active"
            summary = (
                f"{queues.get('review', 0)} in review, {queues.get('approved', 0)} approved, "
                f"{queues.get('draft', 0)} in draft, and {queues.get('sent', 0)} sent."
            )
            metrics = [
                {"label": "review", "value": str(queues.get("review", 0))},
                {"label": "approved", "value": str(queues.get("approved", 0))},
            ]
        elif slug == "client-ops":
            runtime_status = "active"
            summary = (
                f"{client_count} registered clients. Workspace scaffolding and the registry are ready for live intake."
            )
            metrics = [{"label": "clients", "value": str(client_count)}]
        elif slug == "orchestrator":
            orchestrator = orchestrator_summary()
            runtime_status = "active" if orchestrator.get("generated_at") else "planned"
            quotas = orchestrator.get("quotas") if isinstance(orchestrator.get("quotas"), dict) else {}
            summary = (
                f"Growth OS is {orchestrator.get('status') or 'unknown'} with "
                f"{len(orchestrator.get('work_items') or [])} queued work item(s)."
            )
            metrics = [
                {"label": "status", "value": str(orchestrator.get("status") or "missing")},
                {"label": "approved", "value": str(quotas.get("approved_backlog") or 0)},
                {"label": "send gate", "value": "ready" if quotas.get("operator_send_ready") else "held"},
            ]
        elif slug == "intake":
            summary = "Ready to turn transcripts, notes, and messages into structured intake packets once the first live inquiries arrive."
        elif slug == "solution-planning":
            summary = "Planned for converting intake material into scopes, delivery recommendations, and decision-ready project plans."
        elif slug == "delivery":
            summary = "Planned for pilot setup, workflow implementation, and deliverable assembly after scope approval."
        elif slug == "qa-review":
            summary = "Planned for groundedness, citation, and delivery checks before anything sensitive goes out."
        elif slug == "billing-admin":
            summary = "Planned for invoice drafts, payment follow-up prep, and record organization once BOA access is fully live."
        elif slug == "voice-receptionist":
            voice_status = voice_agent_status(limit=2)
            runtime_status = "active" if voice_status.get("app_exists") else "planned"
            summary = (
                f"Inbound-only voice intake scaffold is {voice_status.get('status')}. "
                f"{voice_status.get('intake_count', 0)} intake packet(s) captured."
            )
            metrics = [
                {"label": "mode", "value": str(voice_status.get("status") or "unknown")},
                {"label": "intake", "value": str(voice_status.get("intake_count", 0))},
            ]

        payload["runtime_status"] = runtime_status
        payload["summary"] = summary
        payload["last_run"] = last_run
        payload["metrics"] = metrics
        items.append(payload)

    return items


def agent_summary(items: list[dict[str, object]]) -> dict[str, int]:
    active = sum(1 for item in items if item.get("runtime_status") == "active")
    planned = sum(1 for item in items if item.get("runtime_status") == "planned")
    review_driven = sum(1 for item in items if item.get("mode") == "review-driven")
    autonomous = sum(1 for item in items if item.get("mode") == "autonomous")
    return {
        "total": len(items),
        "active": active,
        "planned": planned,
        "review_driven": review_driven,
        "autonomous": autonomous,
    }


def current_status() -> dict[str, object]:
    lead_status_counts = lead_counts()
    queue_counts = {label: count_json_files(OUTREACH_QUEUE / label) for label in STATUS_LABELS}
    latest_wave = current_wave_summary()
    approved_backlog = approved_backlog_summary()
    approved_backlog_count = int(approved_backlog.get("count") or 0)
    latest_wave_counts = latest_wave.get("packet_counts") or {}
    wave_review_count = int(latest_wave_counts.get("review") or 0)
    wave_approved_count = int(latest_wave_counts.get("approved") or 0)
    wave_sent_count = int(latest_wave_counts.get("sent") or 0)
    client_count = client_registry_count()
    agents = load_agents(lead_status_counts, queue_counts)
    watchdog = watchdog_status_summary()
    tcp_pressure = tcp_pressure_summary()
    auto_send = auto_send_summary()
    operator_alerts = operator_alerts_summary()
    agent_interop = agent_interop_summary()
    orchestrator = orchestrator_summary()
    business_readiness = business_readiness_summary()
    followups = follow_up_summary()
    owned_ops = owned_ops_status()
    next_actions = [
        {
            "title": "Finish Bank of America online access",
            "detail": "The business checking account is approved. The remaining blocker is the mailed password needed for Business Advantage 360 enrollment and final payment instructions.",
            "kind": "banking",
        },
        {
            "title": (
                "Send the approved outreach backlog"
                if approved_backlog_count
                else "Approve the prepared outreach wave"
                if wave_review_count
                else "Prepare the next outreach wave"
            ),
            "detail": (
                f"{approved_backlog_count} approved packet(s) are ready across the backlog; latest wave {latest_wave.get('stem')} has {wave_approved_count} approved packet(s). Final send still requires operator confirmation."
                if approved_backlog_count
                else f"{latest_wave.get('stem')} has {wave_review_count} packets in review, {wave_approved_count} approved, and {wave_sent_count} sent. No automatic prospect send is enabled."
                if wave_review_count
                else "No current wave is ready. Prep can run automatically, but prospect sending still requires an operator confirmation."
            ),
            "kind": "operator-review",
        },
        {
            "title": "Keep the mailbox loop healthy",
            "detail": "Keep inbound import and reviewed reply drafting healthy before widening outreach volume.",
            "kind": "ops-check",
        },
        {
            "title": "Bring inbound voice intake online in dry-run mode",
            "detail": "The receptionist scaffold can capture call/intake packets locally. Live phone use still needs a public webhook URL and provider setup.",
            "kind": "voice-intake",
        },
        {
            "title": "Expand researched targets across legal and accounting",
            "detail": "Keep building the next qualified tranche while the current review wave is still pending.",
            "kind": "lead-research",
        },
        {
            "title": "Validate the next offer: meeting-to-action packets",
            "detail": "The adjacent revenue lane points to speech-to-text / meeting-to-action packets as the easiest add-on demo before widening the offer stack.",
            "kind": "revenue-research",
        },
        {
            "title": (
                "Keep the client registry ready for the first live client"
                if not client_count
                else "Update client milestones and deliverable tracking"
            ),
            "detail": (
                "The registry and workspace scaffolding are ready. The next live win should go through the client-ops path immediately."
                if not client_count
                else f"{client_count} live client record(s) exist. Keep milestones, handoffs, and deliverable status current."
            ),
            "kind": "client-ops",
        },
    ]
    if int(operator_alerts.get("active_count") or 0):
        first_alert = (operator_alerts.get("alerts") or [{}])[0]
        next_actions.insert(
            0,
            {
                "title": "Review prospect reply",
                "detail": f"{first_alert.get('from', 'A prospect')} replied: {first_alert.get('snippet', '')}",
                "kind": "operator-alert",
            },
        )
    if not watchdog.get("ok"):
        next_actions.insert(0, {
            "title": "Fix watchdog findings",
            "detail": f"{watchdog.get('finding_count', 0)} finding(s) are active. Review the Watchdog Status panel before widening outreach or demo traffic.",
            "kind": "watchdog",
        })
    if tcp_pressure.get("severity") == "critical":
        next_actions.insert(0, {
            "title": "Fix M4 TCP pressure before widening traffic",
            "detail": "TCP pressure is critical. Keep sends and demos conservative until loopback and kernel pressure are healthy.",
            "kind": "tcp-pressure",
        })
    elif tcp_pressure.get("severity") == "warning":
        next_actions.insert(1, {
            "title": "Watch M4 TCP pressure",
            "detail": f"TCP pressure is warning-level: TIME_WAIT {tcp_pressure.get('time_wait')}, mbuf use {tcp_pressure.get('mbuf_network_percent')}%. Services are usable, but volume should stay controlled.",
            "kind": "tcp-pressure",
        })
    if auto_send.get("status") in {"blocked", "send-failed"}:
        next_actions.insert(1, {
            "title": "Review auto-send status",
            "detail": str(auto_send.get("block_reason") or "Auto-send did not complete cleanly."),
            "kind": "auto-send",
        })
    if not business_readiness.get("ok"):
        next_actions.insert(1, {
            "title": "Review business readiness findings",
            "detail": "; ".join(str(item) for item in (business_readiness.get("findings") or [])[:3]) or "The readiness sweep has findings.",
            "kind": "business-readiness",
        })
    for item in reversed((orchestrator.get("work_items") or [])[:3]):
        if not isinstance(item, dict):
            continue
        next_actions.insert(1, {
            "title": str(item.get("title") or "Orchestrator work item"),
            "detail": str(item.get("recommended_action") or item.get("detail") or "Review the Growth OS panel."),
            "kind": f"growth-os:{item.get('lane') or 'orchestrator'}",
        })
    if int(followups.get("review_queue") or 0):
        next_actions.insert(2, {
            "title": "Review staged follow-ups",
            "detail": f"{followups.get('review_queue')} follow-up packet(s) are staged for no-reply prospects. Review before approving or sending.",
            "kind": "follow-up",
        })
    elif int(followups.get("eligible_count") or 0):
        next_actions.insert(2, {
            "title": "Stage first follow-ups for older no-reply sends",
            "detail": f"{followups.get('eligible_count')} sent prospect(s) are at least {followups.get('min_age_days')} days old with no tracked reply or follow-up.",
            "kind": "follow-up",
        })
    if int(operator_alerts.get("active_count") or 0):
        first_alert = (operator_alerts.get("alerts") or [{}])[0]
        next_actions = [item for item in next_actions if item.get("kind") != "operator-alert"]
        next_actions.insert(
            0,
            {
                "title": "Review prospect reply",
                "detail": f"{first_alert.get('from', 'A prospect')} replied: {first_alert.get('snippet', '')}",
                "kind": "operator-alert",
            },
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panel_urls": {
            "local": "http://127.0.0.1:8042",
            "tailscale": "https://m4-mac-mini.tailee4a3f.ts.net/",
        },
        "site_urls": {
            "public": "https://jvt-technologies.com",
            "www": "https://www.jvt-technologies.com",
        },
        "demo_urls": {
            "product_readme": str(REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "private-doc-intel-demo" / "README.md"),
            "local_demo_path": "/demo",
        },
        "voice_agent": voice_agent_status(),
        "owned_ops": owned_ops,
        "revenue_opportunities": revenue_opportunities(),
        "crypto_lab": crypto_lab_status(),
        "watchdog": watchdog,
        "tcp_pressure": tcp_pressure,
        "auto_send": auto_send,
        "operator_alerts": operator_alerts,
        "agent_interop": agent_interop,
        "orchestrator": orchestrator,
        "business_readiness": business_readiness,
        "follow_up_pipeline": followups,
        "lead_counts": lead_status_counts,
        "agent_summary": agent_summary(agents),
        "queue_counts": queue_counts,
        "sent_packet_breakdown": sent_packet_breakdown(),
        "current_wave": latest_wave,
        "approved_backlog": approved_backlog,
        "inbox_counts": {
            "new": count_json_files_recursive(INBOX_ROOT / "new"),
            "reviewed": count_json_files_recursive(INBOX_ROOT / "reviewed"),
            "closed": count_json_files_recursive(INBOX_ROOT / "closed"),
        },
        "inbox_buckets": inbox_bucket_counts(),
        "inbox_buckets_all": inbox_bucket_counts(("new", "reviewed", "closed")),
        "decision_counts": {label: count_json_files(CONTROL_ROOT / label) for label in DECISION_LABELS},
        "pending_decisions": json_stems(CONTROL_ROOT / "pending"),
        "next_actions": next_actions,
    }


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "decision"


def create_decision(request: DecisionCreateRequest) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    stem = f"{now.strftime('%Y-%m-%d')}-{slugify(request.title)}"
    pending_dir = CONTROL_ROOT / "pending"
    json_path = pending_dir / f"{stem}.json"
    md_path = pending_dir / f"{stem}.md"
    pending_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": "pending",
        "category": request.category,
        "title": request.title,
        "recommended_action": request.recommended_action,
        "context": request.context,
        "risk": request.risk,
        "options": request.options,
        "created_at": now.isoformat(),
        "stem": stem,
        "paths": {
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    option_lines = "\n".join(f"- {option}" for option in request.options) if request.options else "- Accept the recommended action"
    md_path.write_text(
        "\n".join(
            [
                f"# {request.title}",
                "",
                f"- Category: `{request.category}`",
                "- Status: `pending`",
                f"- Risk: `{request.risk}`",
                f"- Created: `{now.isoformat()}`",
                "",
                "## Recommended Action",
                "",
                request.recommended_action,
                "",
                "## Context",
                "",
                request.context or "No extra context provided.",
                "",
                "## Options",
                "",
                option_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return payload


def transition_decision(stem: str, request: DecisionTransitionRequest) -> dict[str, object]:
    source_json = None
    source_md = None
    source_state = None
    for label in DECISION_LABELS:
        candidate_json = CONTROL_ROOT / label / f"{stem}.json"
        candidate_md = CONTROL_ROOT / label / f"{stem}.md"
        if candidate_json.exists():
            source_json = candidate_json
            source_md = candidate_md
            source_state = label
            break

    if source_json is None or source_md is None or source_state is None:
        raise HTTPException(status_code=404, detail=f"Decision packet not found: {stem}")

    payload = json.loads(source_json.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).isoformat()
    payload["status"] = request.state
    payload["operator_note"] = request.note
    payload["updated_at"] = now

    target_dir = CONTROL_ROOT / request.state
    target_dir.mkdir(parents=True, exist_ok=True)
    target_json = target_dir / source_json.name
    target_md = target_dir / source_md.name

    target_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    source_json.unlink()

    markdown = source_md.read_text(encoding="utf-8").rstrip() + f"\n\n## Decision Update\n\n- New status: `{request.state}`\n- Updated: `{now}`\n- Note: {request.note or 'No note provided.'}\n"
    target_md.write_text(markdown + "\n", encoding="utf-8")
    source_md.unlink()

    log_path = CONTROL_ROOT / "decision-log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "stem": stem,
            "from_state": source_state,
            "to_state": request.state,
            "note": request.note,
            "updated_at": now,
        }) + "\n")

    return {
        "stem": stem,
        "from_state": source_state,
        "to_state": request.state,
        "json_path": str(target_json),
        "markdown_path": str(target_md),
    }


def active_model_path(profile: str) -> Path:
    if profile == "reviewer":
        return REVIEWER_MODEL_PATH
    if profile == "strong":
        return STRONG_MODEL_PATH
    return FAST_MODEL_PATH


def load_model(profile: str):
    model_path = active_model_path(profile)
    if not model_path.exists():
        raise HTTPException(status_code=500, detail=f"Local model path does not exist: {model_path}")

    with _MODEL_LOCK:
        cached_profile = _ACTIVE_MODEL.get("profile")
        if cached_profile == profile and _ACTIVE_MODEL.get("model") and _ACTIVE_MODEL.get("tokenizer"):
            return _ACTIVE_MODEL["model"], _ACTIVE_MODEL["tokenizer"], str(model_path)

        from mlx_lm import load

        model, tokenizer = load(str(model_path))
        _ACTIVE_MODEL.clear()
        _ACTIVE_MODEL.update({
            "profile": profile,
            "model": model,
            "tokenizer": tokenizer,
            "path": str(model_path),
        })
        return model, tokenizer, str(model_path)


def build_model_prompt(prompt: str, include_status_context: bool) -> str:
    system = (
        "You are the local JVT Technologies operator copilot running on the Mac mini. "
        "Help with outreach, site operations, demos, control-panel decisions, and practical business operations. "
        "Be concise, risk-aware, and action-oriented. If something should wait for operator approval, say so clearly. "
        "Do not ask follow-up questions unless the operator is truly blocked. Do not repeat yourself. "
        "Respond in short practical prose, not in a transcript."
    )
    lines = [system, ""]
    if include_status_context:
        lines.extend([
            "Current system snapshot:",
            json.dumps(current_status(), indent=2),
            "",
        ])
    lines.extend([
        "Operator request:",
        prompt.strip(),
        "",
        "Response:",
    ])
    return "\n".join(lines)


def clean_model_response(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\bIs this clear\?.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"\bHere'?s a concise summary:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    if len(sentences) > 3:
        cleaned = " ".join(sentences[:3]).strip()
    return cleaned


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "app": "jvt-control-panel",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


@app.get("/api/status")
def api_status() -> dict[str, object]:
    return current_status()


@app.get("/api/agents")
def api_agents() -> dict[str, object]:
    return {"items": load_agents()}


@app.get("/api/agent-interop")
def api_agent_interop() -> dict[str, object]:
    return agent_interop_summary()


@app.get("/api/orchestrator/status")
def api_orchestrator_status() -> dict[str, object]:
    return orchestrator_summary()


@app.get("/api/growth-ops/checkin")
def api_growth_ops_checkin() -> dict[str, object]:
    return growth_checkin_summary()


@app.get("/api/business-readiness")
def api_business_readiness() -> dict[str, object]:
    return business_readiness_summary()


@app.get("/api/ops/owned-status")
def api_owned_ops_status() -> dict[str, object]:
    return owned_ops_status()


@app.get("/api/voice/status")
def api_voice_status() -> dict[str, object]:
    return voice_agent_status()


@app.get("/api/revenue-opportunities")
def api_revenue_opportunities(limit: int = 5) -> dict[str, object]:
    return revenue_opportunities(limit=limit)


@app.get("/api/crypto-lab/status")
def api_crypto_lab_status() -> dict[str, object]:
    return crypto_lab_status()


@app.post("/api/crypto-lab/refresh")
def api_crypto_lab_refresh(offline: bool = False) -> dict[str, object]:
    return run_crypto_lab(offline=offline)


@app.get("/api/leads")
def api_leads(limit: int = 10) -> dict[str, object]:
    return {"items": recent_leads(limit=limit)}


@app.get("/api/outreach/recent")
def api_recent_outreach(limit: int = 8) -> dict[str, object]:
    return {
        "draft": recent_packets(OUTREACH_QUEUE / "draft", limit=limit),
        "review": recent_packets(OUTREACH_QUEUE / "review", limit=limit),
        "approved": recent_packets(OUTREACH_QUEUE / "approved", limit=limit),
        "sent": recent_packets(OUTREACH_QUEUE / "sent", limit=limit),
    }


@app.get("/api/outreach/waves")
def api_outreach_waves(limit: int = 8) -> dict[str, object]:
    return {"items": list_outreach_waves(limit=limit)}


@app.post("/api/outreach/waves/prepare")
def api_prepare_outreach_wave(request: OutreachWavePrepareRequest) -> dict[str, object]:
    return prepare_daily_wave(request)


@app.post("/api/outreach/waves/{wave_stem}/approve")
def api_approve_outreach_wave(wave_stem: str) -> dict[str, object]:
    return approve_outreach_wave(wave_stem)


@app.post("/api/outreach/waves/{wave_stem}/send")
def api_send_outreach_wave(wave_stem: str, request: OutreachWaveSendRequest) -> dict[str, object]:
    return send_outreach_wave(wave_stem, request.confirmed)


@app.get("/api/outreach/{queue_label}/{stem}")
def api_outreach_detail(queue_label: str, stem: str) -> dict[str, object]:
    return packet_detail(queue_label, stem)


@app.post("/api/outreach/{queue_label}/{stem}/transition")
def api_outreach_transition(queue_label: str, stem: str, request: OutreachTransitionRequest) -> dict[str, object]:
    return move_outreach_packet(queue_label, request.target_state, stem)


@app.post("/api/outreach/send")
def api_outreach_send(request: OutreachSendRequest) -> dict[str, object]:
    return send_outreach_packets(request.stems, request.confirmed)


@app.get("/api/inbox/recent")
def api_recent_inbox(limit: int = 8) -> dict[str, object]:
    return {"items": recent_inbox_messages(limit=limit)}


@app.post("/api/inbox/{stem}/transition")
def api_inbox_transition(stem: str, request: InboxTransitionRequest) -> dict[str, object]:
    return move_inbox_message(stem, request.target_state)


@app.get("/api/decisions")
def api_decisions() -> dict[str, object]:
    return {
        label: list_decisions(label)
        for label in DECISION_LABELS
    }


@app.post("/api/decisions")
def api_create_decision(request: DecisionCreateRequest) -> dict[str, object]:
    return create_decision(request)


@app.post("/api/decisions/{stem}/transition")
def api_transition_decision(stem: str, request: DecisionTransitionRequest) -> dict[str, object]:
    return transition_decision(stem, request)


@app.post("/api/model/respond")
def api_model_respond(request: ModelPromptRequest) -> dict[str, object]:
    model, tokenizer, model_path = load_model(request.profile)
    prompt = build_model_prompt(request.prompt, request.include_status_context)

    from mlx_lm import generate

    response_text = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=request.max_tokens,
        verbose=False,
    ).strip()

    return {
        "profile": request.profile,
        "model_path": model_path,
        "response": clean_model_response(response_text),
    }
