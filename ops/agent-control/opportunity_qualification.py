#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MAILBOX_AGENT_ROOT = REPO_ROOT / "outreach" / "mailbox-agent"
if str(MAILBOX_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MAILBOX_AGENT_ROOT))

from inbox_policy import is_internal_sender, is_system_sender

WARM_STAGES = {
    "inbound-hit-needs-review",
    "reply-needs-response",
    "proposal-needed",
    "pilot-discovery-needed",
    "reply-sent-awaiting-next",
    "active",
}

ACTIVE_STAGES = WARM_STAGES - {"reply-sent-awaiting-next"}

INTERNAL_MARKERS = {
    "operator_or_internal_sender",
    "reviewed_internal",
}

DISQUALIFIED_MARKERS = {
    "closed_promotional_or_newsletter",
    "promotional_or_newsletter_marker",
    "newsletter",
    "promotional",
    "unsubscribe",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_source_path(source: str, repo_root: Path) -> Path | None:
    if not source:
        return None
    source_path = Path(source)
    if source_path.exists():
        return source_path
    if not source_path.name:
        return None

    inbox_root = repo_root / "outreach" / "inbox"
    matches = list(inbox_root.glob(f"**/{source_path.name}")) if inbox_root.exists() else []
    if not matches:
        return None

    rank = {"reviewed": 0, "closed": 1, "new": 2}
    matches.sort(
        key=lambda path: min(
            (rank.get(part, 9) for part in path.parts),
            default=9,
        )
    )
    return matches[0]


def source_payload(source: str, repo_root: Path) -> tuple[dict[str, Any], Path | None]:
    path = resolve_source_path(source, repo_root)
    if path is None or path.suffix.lower() != ".json":
        return {}, path
    return load_json(path), path


def _normalized_text(*values: Any) -> str:
    return " ".join(str(value or "").strip().lower() for value in values)


def _message_identity(item: dict[str, Any], payload: dict[str, Any], source_path: Path | None) -> str:
    uid = payload.get("uid") or payload.get("message_uid")
    if uid not in (None, ""):
        return f"mail-uid:{uid}"

    message_id = re.sub(r"\s+", "", str(payload.get("message_id") or "")).lower()
    if message_id:
        return f"message-id:{message_id}"

    filename = source_path.name if source_path else Path(str(item.get("source") or "")).name
    match = re.search(r"uid-(\d+)", filename)
    if match:
        return f"mail-uid:{match.group(1)}"

    contact = str(item.get("contact_email") or "").strip().lower()
    subject = str(payload.get("subject") or item.get("source_subject") or "").strip().lower()
    if contact or subject:
        return f"contact:{contact}|subject:{subject}"

    return "record:" + "|".join(
        [
            str(item.get("kind") or "opportunity"),
            str(item.get("id") or ""),
            str(item.get("account_name") or "").strip().lower(),
        ]
    )


def _classify(
    item: dict[str, Any],
    payload: dict[str, Any],
    source_path: Path | None,
) -> tuple[str, list[str]]:
    if item.get("kind") == "pilot_decision":
        return "concept", ["no_confirmed_contact"]

    status = _normalized_text(
        payload.get("agent_triage_status"),
        payload.get("agent_triage_reason"),
        payload.get("classification"),
        payload.get("category"),
        payload.get("closed_reason"),
    )
    source_text = str(source_path or item.get("source") or "").lower()
    account_text = _normalized_text(item.get("account_name"), item.get("contact_email"))
    email = str(item.get("contact_email") or payload.get("sender_email") or "").strip().lower()

    if any(marker in status for marker in INTERNAL_MARKERS):
        return "internal", ["source_marked_internal"]
    if "vasudevan chandrabose" in account_text or is_internal_sender(email):
        return "internal", ["known_internal_test_contact"]
    if is_system_sender(email):
        return "disqualified", ["known_system_sender"]

    if any(marker in status for marker in DISQUALIFIED_MARKERS):
        return "disqualified", ["source_marked_promotional_or_closed"]
    if "/closed/" in source_text:
        return "disqualified", ["source_moved_to_closed_inbox"]

    if not email or "@" not in email:
        return "unqualified", ["missing_confirmed_contact"]

    stage = str(item.get("stage") or "").strip().lower()
    if stage not in WARM_STAGES:
        return "inactive", ["stage_not_warm"]

    return "qualified", ["external_contact_and_warm_stage"]


def qualify_items(items: list[dict[str, Any]], repo_root: Path) -> list[dict[str, Any]]:
    qualified: list[dict[str, Any]] = []
    seen: dict[str, Any] = {}

    for raw in items:
        item = dict(raw)
        payload, resolved_path = source_payload(str(item.get("source") or ""), repo_root)
        identity = _message_identity(item, payload, resolved_path)
        status, reasons = _classify(item, payload, resolved_path)
        duplicate_of = seen.get(identity)
        if duplicate_of is None:
            seen[identity] = item.get("id") or len(seen) + 1

        item["source_resolved"] = str(resolved_path or "")
        item["source_subject"] = payload.get("subject") or item.get("source_subject") or ""
        item["source_snippet"] = (
            payload.get("snippet")
            or payload.get("body_preview")
            or item.get("source_snippet")
            or ""
        )
        item["source_from"] = payload.get("from") or payload.get("sender") or item.get("source_from") or ""
        item["source_uid"] = payload.get("uid") or payload.get("message_uid") or ""
        item["source_message_id"] = payload.get("message_id") or ""
        item["qualification_status"] = status
        item["qualification_reasons"] = reasons
        item["dedupe_key"] = identity
        item["duplicate"] = duplicate_of is not None
        item["duplicate_of"] = duplicate_of
        item["qualified"] = status == "qualified" and duplicate_of is None
        item["warm"] = item["qualified"]
        item["active"] = item["qualified"] and str(item.get("stage") or "") in ACTIVE_STAGES
        item["conversion_stage"] = _conversion_stage(item)
        qualified.append(item)

    return qualified


def _conversion_stage(item: dict[str, Any]) -> str:
    if item.get("duplicate"):
        return "duplicate"
    status = str(item.get("qualification_status") or "")
    if status != "qualified":
        return status or "unqualified"
    return {
        "inbound-hit-needs-review": "qualified",
        "reply-needs-response": "qualified",
        "reply-sent-awaiting-next": "qualified-awaiting-next",
        "proposal-needed": "proposal-ready",
        "pilot-discovery-needed": "discovery",
        "active": "active-client",
    }.get(str(item.get("stage") or ""), "qualified")
