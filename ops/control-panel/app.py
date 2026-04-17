#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal

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
INBOX_ROOT = REPO_ROOT / "outreach" / "inbox"
CONTROL_ROOT = REPO_ROOT / "ops" / "agent-control"
STATUS_LABELS = ("draft", "review", "approved", "sent", "replied")
DECISION_LABELS = ("pending", "approved", "rejected", "executed")

FAST_MODEL_PATH = Path("/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--Qwen2.5-3B-Instruct-4bit")
STRONG_MODEL_PATH = Path("/Users/c.s.d.v.r.s./Library/Caches/Private-AI-Lab/models/answers/mlx-community--Qwen2.5-7B-Instruct-4bit")

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
    profile: Literal["fast", "strong"] = "fast"
    include_status_context: bool = True
    max_tokens: int = Field(default=260, ge=64, le=600)


class OutreachTransitionRequest(BaseModel):
    target_state: Literal["draft", "review", "approved"]


class OutreachSendRequest(BaseModel):
    stems: list[str] = Field(default_factory=list)
    confirmed: bool = False


_MODEL_LOCK = Lock()
_ACTIVE_MODEL: dict[str, object] = {}
SEND_SCRIPT = REPO_ROOT / "outreach" / "tools" / "send_approved.py"


def count_json_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len([path for path in directory.glob("*.json") if path.is_file()])


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


def send_outreach_packets(stems: list[str], confirmed: bool) -> dict[str, object]:
    unique_stems = list(dict.fromkeys(stems))
    if not unique_stems:
        raise HTTPException(status_code=400, detail="Provide at least one approved packet to send")
    if not confirmed:
        raise HTTPException(status_code=400, detail="Send confirmation required")

    command = ["python3", str(SEND_SCRIPT)]
    for stem in unique_stems:
        command.extend(["--stem", stem])
    command.append("--send")

    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
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


def recent_inbox_messages(limit: int = 8) -> list[dict[str, object]]:
    candidates: list[Path] = []
    for label in ("new", "reviewed", "closed"):
        directory = INBOX_ROOT / label
        if directory.exists():
            candidates.extend(path for path in directory.rglob("*.json") if path.is_file())
    ordered = sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[:limit]
    messages: list[dict[str, object]] = []
    for path in ordered:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["path"] = str(path)
        messages.append(payload)
    return messages


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


def current_status() -> dict[str, object]:
    queue_counts = {label: count_json_files(OUTREACH_QUEUE / label) for label in STATUS_LABELS}
    review_count = queue_counts.get("review", 0)
    approved_count = queue_counts.get("approved", 0)
    approved_decision_count = count_json_files(CONTROL_ROOT / "approved")
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
        "lead_counts": lead_counts(),
        "queue_counts": queue_counts,
        "inbox_counts": {
            "new": count_json_files(INBOX_ROOT / "new"),
            "reviewed": count_json_files(INBOX_ROOT / "reviewed"),
            "closed": count_json_files(INBOX_ROOT / "closed"),
        },
        "decision_counts": {label: count_json_files(CONTROL_ROOT / label) for label in DECISION_LABELS},
        "pending_decisions": json_stems(CONTROL_ROOT / "pending"),
        "next_actions": [
            {
                "title": "Confirm legal entity and EIN",
                "detail": "This is the real blocker before Mercury and Stripe can be opened cleanly.",
                "kind": "company-blocker",
            },
            {
                "title": (
                    "Send the approved outreach batch"
                    if approved_count
                    else
                    "Decision approved; send or reduce the staged outreach wave"
                    if approved_decision_count and review_count
                    else "Review the prepared outreach wave"
                    if review_count
                    else "Approve the next reviewed outreach batch"
                ),
                "detail": (
                    f"{approved_count} packets are staged in approved and ready for a confirmed send."
                    if approved_count
                    else
                    f"The approval came through, but {review_count} packets are still waiting in the review queue and have not been sent yet."
                    if approved_decision_count and review_count
                    else f"{review_count} refreshed packets are waiting in the review queue."
                    if review_count
                    else "One pending decision already exists for the next national send tranche."
                ),
                "kind": "operator-review",
            },
            {
                "title": "Run one live inbound and outbound mailbox check",
                "detail": "Keep the send/receive loop healthy before widening outreach volume.",
                "kind": "ops-check",
            },
            {
                "title": "Open Mercury and Stripe after entity readiness",
                "detail": "Run a self-test invoice before real client billing.",
                "kind": "finance-setup",
            },
            {
                "title": "Expand the next national lead tranche",
                "detail": "Keep adding qualified U.S. firms while the current five-company review wave is pending.",
                "kind": "lead-research",
            },
        ],
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
    return STRONG_MODEL_PATH if profile == "strong" else FAST_MODEL_PATH


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
