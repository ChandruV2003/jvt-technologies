#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sqlite3
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


_MODEL_LOCK = Lock()
_ACTIVE_MODEL: dict[str, object] = {}


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
        payload["path"] = str(path)
        packets.append(payload)
    return packets


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
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_urls": {
            "public": "https://jvt-technologies.com",
            "www": "https://www.jvt-technologies.com",
        },
        "demo_urls": {
            "product_readme": str(REPO_ROOT / "products" / "Private-AI-Lab" / "apps" / "private-doc-intel-demo" / "README.md"),
            "local_demo_path": "/demo",
        },
        "lead_counts": lead_counts(),
        "queue_counts": {label: count_json_files(OUTREACH_QUEUE / label) for label in STATUS_LABELS},
        "inbox_counts": {
            "new": count_json_files(INBOX_ROOT / "new"),
            "reviewed": count_json_files(INBOX_ROOT / "reviewed"),
            "closed": count_json_files(INBOX_ROOT / "closed"),
        },
        "decision_counts": {label: count_json_files(CONTROL_ROOT / label) for label in DECISION_LABELS},
        "pending_decisions": json_stems(CONTROL_ROOT / "pending"),
        "next_actions": [
            {
                "title": "Enable Tailscale Serve",
                "detail": "Required once on the tailnet before the control panel can be reached remotely.",
                "kind": "human-blocker",
            },
            {
                "title": "Confirm legal entity and EIN",
                "detail": "This is the real blocker before Mercury and Stripe can be opened cleanly.",
                "kind": "company-blocker",
            },
            {
                "title": "Approve the next reviewed outreach batch",
                "detail": "One pending decision already exists for the next national send tranche.",
                "kind": "operator-review",
            },
            {
                "title": "Open Mercury and Stripe after entity readiness",
                "detail": "Run a self-test invoice before real client billing.",
                "kind": "finance-setup",
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
        "sent": recent_packets(OUTREACH_QUEUE / "sent", limit=limit),
    }


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
