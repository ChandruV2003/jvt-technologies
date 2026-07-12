#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
QUEUE_ROOT = REPO_ROOT / "outreach" / "queue"
OUTPUT_ROOT = REPO_ROOT / "client-work" / "followup-samples"
STATE_ROOT = REPO_ROOT / "ops" / "agent-control" / "state"
REPORT_JSON = STATE_ROOT / "latest-warm-followup-samples.json"
REPORT_MD = STATE_ROOT / "latest-warm-followup-samples.md"

INTERNAL_RECIPIENTS = {
    "chandruvasu@icloud.com",
    "chandruv@icloud.com",
    "chandru@jvt-technologies.com",
    "chandruv@jvt-technologies.com",
    "hello@jvt-technologies.com",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_slug() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_datetime(value: Any) -> datetime | None:
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
    return parsed.astimezone(timezone.utc)


def is_prospect_packet(payload: dict[str, Any]) -> bool:
    recipient = str(payload.get("recipient_email") or "").strip().lower()
    company = str(payload.get("company_name") or "").strip().lower()
    if not recipient or "@" not in recipient:
        return False
    return not (
        recipient in INTERNAL_RECIPIENTS
        or recipient.endswith("@jvt-technologies.com")
        or "jvt technologies" in company
        or company in {"test", "self-test"}
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:90] or "prospect"


def next_stage(payload: dict[str, Any]) -> int:
    raw = payload.get("follow_up_stage")
    try:
        stage = int(raw or 0)
    except (TypeError, ValueError):
        stage = 0
    return min(stage + 1, 3)


def lane_for(payload: dict[str, Any]) -> str:
    text = " ".join(
        str(payload.get(key) or "")
        for key in ("industry", "practice_area", "primary_focus", "lead_context", "personalized_offer")
    ).lower()
    if any(token in text for token in ("dental", "healthcare", "patient", "appointment")):
        return "ai-voice-intake"
    if any(token in text for token in ("title", "mortgage", "real estate closing")):
        return "title-document-workflow"
    if any(token in text for token in ("construction", "contractor", "roofing")):
        return "field-ops-document-workflow"
    if any(token in text for token in ("property management", "hoa", "condo", "tenant")):
        return "property-ops-workflow"
    if any(token in text for token in ("tax", "accounting", "bookkeeping", "cpa", "cas")):
        return "firm-knowledge-assistant"
    if any(token in text for token in ("law", "legal", "attorney", "estate", "litigation")):
        return "private-document-assistant"
    if any(token in text for token in ("ballot", "board meeting", "av", "it consulting")):
        return "agentic-workflow-automation"
    return "workflow-cleanup"


LANE_COPY = {
    "ai-voice-intake": {
        "subject": "Tiny missed-call intake demo for {company}",
        "angle": "one disclosed voice intake flow that turns missed calls into staff review packets",
        "proof": "a synthetic missed-call packet with caller details, request type, urgency, and callback info",
    },
    "title-document-workflow": {
        "subject": "Small title workflow sample for {company}",
        "angle": "one review-first document workflow for repeated closing/title admin questions",
        "proof": "a synthetic title/order packet with source notes, missing info, and a draft staff response",
    },
    "field-ops-document-workflow": {
        "subject": "Small ops packet idea for {company}",
        "angle": "one field/admin workflow that turns repeated requests into a checklist, packet, and draft response",
        "proof": "a synthetic job/admin packet showing missing info, owner, due date, and review status",
    },
    "property-ops-workflow": {
        "subject": "Small property ops workflow sample for {company}",
        "angle": "one resident/vendor/board request workflow that creates a reviewed task packet",
        "proof": "a synthetic property ops packet with request summary, documents needed, and next action",
    },
    "firm-knowledge-assistant": {
        "subject": "Small internal knowledge sample for {company}",
        "angle": "one private SOP/client-reference assistant that answers from approved material with source links",
        "proof": "a synthetic client-service packet with source references, draft answer, and review notes",
    },
    "private-document-assistant": {
        "subject": "Small document workflow sample for {company}",
        "angle": "one private document workflow that finds source material and drafts a review-only answer",
        "proof": "a synthetic document packet with cited source notes, missing info, and a draft response",
    },
    "agentic-workflow-automation": {
        "subject": "Narrow workflow automation sample for {company}",
        "angle": "one repeat workflow mapped into intake, checklist, draft, approval, and audit steps",
        "proof": "a synthetic workflow packet with intake summary, staff tasks, and an approval trail",
    },
    "workflow-cleanup": {
        "subject": "Small workflow cleanup sample for {company}",
        "angle": "one repeated workflow cleaned into a review-first packet and draft response",
        "proof": "a synthetic packet showing the before/after shape without touching live data",
    },
}


def build_sample(payload: dict[str, Any], source_path: Path) -> dict[str, Any]:
    company = str(payload.get("company_name") or source_path.stem).strip()
    lane = lane_for(payload)
    copy = LANE_COPY.get(lane, LANE_COPY["workflow-cleanup"])
    sent_at = str(payload.get("sent_at") or payload.get("generated_at") or "")
    intro_offer = str(payload.get("personalized_offer") or "").strip()
    likely_pain = str(payload.get("likely_pain") or "").strip()
    proof = copy["proof"]
    angle = copy["angle"]
    stage = next_stage(payload)
    subject = copy["subject"].format(company=company)
    body = "\n".join(
        [
            f"Hi {company} team,",
            "",
            "Quick follow-up, not trying to turn this into a giant AI platform pitch.",
            "",
            f"The smaller version I had in mind is {angle}.",
            f"I can mock up {proof} using only synthetic data, so there is no risk to live client/customer material.",
            "",
            "If it is useful, I can send the one-page sample first and you can decide if it is worth a short workflow call.",
            "",
            "Chandru",
        ]
    )
    return {
        "company_name": company,
        "recipient_email": str(payload.get("recipient_email") or "").strip(),
        "industry": str(payload.get("industry") or "unknown").strip() or "unknown",
        "primary_focus": str(payload.get("primary_focus") or "").strip(),
        "lane": lane,
        "next_followup_stage": stage,
        "last_sent_at": sent_at,
        "last_subject": str(payload.get("subject") or "").strip(),
        "source_packet": str(source_path.relative_to(REPO_ROOT)),
        "fit_score": payload.get("fit_score"),
        "likely_pain": likely_pain,
        "original_offer": intro_offer,
        "sample_subject": subject,
        "sample_body": body,
        "review_status": "review-only",
    }


def latest_prospect_packets() -> list[tuple[Path, dict[str, Any]]]:
    sent_dir = QUEUE_ROOT / "sent"
    if not sent_dir.exists():
        return []
    by_key: dict[str, tuple[Path, dict[str, Any], datetime | None]] = {}
    for path in sorted(sent_dir.glob("*.json")):
        payload = load_json(path, {})
        if not isinstance(payload, dict) or not is_prospect_packet(payload):
            continue
        key = "|".join(
            [
                str(payload.get("recipient_email") or "").strip().lower(),
                slugify(str(payload.get("company_name") or path.stem)),
            ]
        )
        sent_at = parse_datetime(payload.get("sent_at") or payload.get("generated_at"))
        existing = by_key.get(key)
        if not existing or (sent_at or datetime.min.replace(tzinfo=timezone.utc)) > (existing[2] or datetime.min.replace(tzinfo=timezone.utc)):
            by_key[key] = (path, payload, sent_at)
    return [(path, payload) for path, payload, _sent_at in sorted(by_key.values(), key=lambda item: str(item[1].get("company_name") or ""))]


def build_report() -> dict[str, Any]:
    samples = [build_sample(payload, path) for path, payload in latest_prospect_packets()]
    lane_counts = Counter(sample["lane"] for sample in samples)
    industry_counts = Counter(sample["industry"] for sample in samples)
    output_json = OUTPUT_ROOT / f"warm-followup-samples-{today_slug()}.json"
    output_md = OUTPUT_ROOT / f"warm-followup-samples-{today_slug()}.md"
    report = {
        "generated_at": utc_now(),
        "ok": True,
        "sent_company_count": len(samples),
        "sample_count": len(samples),
        "lane_counts": dict(sorted(lane_counts.items())),
        "industry_counts": dict(industry_counts.most_common()),
        "sample_json_path": str(output_json),
        "sample_markdown_path": str(output_md),
        "samples": samples,
        "guardrail": "Review-only follow-up sample preparation. No packet approval, queue movement, external sending, provider action, or commitment.",
    }
    write_json(output_json, report)
    write_markdown(report, output_md)
    return report


def write_markdown(report: dict[str, Any], path: Path) -> None:
    samples = report.get("samples") if isinstance(report.get("samples"), list) else []
    lines = [
        "# Warm Follow-Up Samples",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Reached prospect/company records covered: `{report['sent_company_count']}`",
        f"- Samples prepared: `{report['sample_count']}`",
        f"- Guardrail: {report['guardrail']}",
        "",
        "These are review-only warm follow-up samples for prospects already contacted. They are not send-ready and do not move anything into the outreach queue.",
        "",
        "## Lane Counts",
        "",
    ]
    for lane, count in sorted((report.get("lane_counts") or {}).items()):
        lines.append(f"- `{lane}`: {count}")
    lines.extend(["", "## Industry Counts", ""])
    for industry, count in list((report.get("industry_counts") or {}).items())[:20]:
        lines.append(f"- `{industry}`: {count}")
    lines.extend(["", "## Company Samples", ""])
    for index, sample in enumerate(samples, start=1):
        lines.extend(
            [
                f"### {index}. {sample['company_name']}",
                "",
                f"- Recipient: `{sample['recipient_email']}`",
                f"- Lane: `{sample['lane']}`",
                f"- Industry: {sample['industry']}",
                f"- Last sent: `{sample['last_sent_at']}`",
                f"- Source: `{sample['source_packet']}`",
                f"- Review status: `{sample['review_status']}`",
                "",
                f"Subject: {sample['sample_subject']}",
                "",
                "```text",
                sample["sample_body"],
                "```",
                "",
            ]
        )
    if not samples:
        lines.append("No sent prospect packets were available.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_state(report: dict[str, Any]) -> None:
    state = dict(report)
    samples = state.get("samples") if isinstance(state.get("samples"), list) else []
    state["samples"] = samples[:80]
    state["sample_preview_count"] = len(state["samples"])
    write_json(REPORT_JSON, state)

    lines = [
        "# Warm Follow-Up Sample Prep",
        "",
        f"- Generated: `{state['generated_at']}`",
        f"- Reached prospect/company records covered: `{state['sent_company_count']}`",
        f"- Samples prepared: `{state['sample_count']}`",
        f"- Full JSON: `{state['sample_json_path']}`",
        f"- Full Markdown: `{state['sample_markdown_path']}`",
        f"- Guardrail: {state['guardrail']}",
        "",
        "## Top Lanes",
        "",
    ]
    for lane, count in sorted((state.get("lane_counts") or {}).items(), key=lambda item: item[1], reverse=True):
        lines.append(f"- `{lane}`: {count}")
    lines.extend(["", "## First 12 Review Samples", ""])
    for sample in samples[:12]:
        lines.append(f"- {sample['company_name']} / `{sample['lane']}` / `{sample['recipient_email']}` / {sample['sample_subject']}")
    if not samples:
        lines.append("- None.")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    write_state(report)
    print(json.dumps({"ok": True, "sent_company_count": report["sent_company_count"], "sample_count": report["sample_count"]}))


if __name__ == "__main__":
    main()
