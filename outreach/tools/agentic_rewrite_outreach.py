#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from email_theme import DEFAULT_REPLY_TO, DEFAULT_SITE_URL, render_text_email_html
from model_copywriter import packet_type_for, rewrite_email


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
QUEUE_ROOT = ROOT / "outreach" / "queue"
REPORT_DIR = ROOT / "outreach" / "schedules" / "copywriter"


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def is_followup(payload: dict[str, Any]) -> bool:
    return bool(payload.get("follow_up_stage") or payload.get("follow_up_parent_stem") or "follow-up" in str(payload.get("template") or "").lower())


def rewrite_markdown(path: Path, subject: str, body: str) -> None:
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"(?m)^# .+$", content):
        content = re.sub(r"(?m)^# .+$", f"# {subject}", content, count=1)
        before, _, _old = content.partition(f"# {subject}")
        front = before + f"# {subject}\n\n"
        path.write_text(front + body.strip() + "\n", encoding="utf-8")
        return
    path.write_text(body.strip() + "\n", encoding="utf-8")


def update_packet(metadata_path: Path, *, write: bool) -> dict[str, Any]:
    payload = load_json(metadata_path)
    if not payload:
        return {"stem": metadata_path.stem, "status": "skipped", "reason": "metadata parse failed"}
    text_path = metadata_path.with_suffix(".txt")
    if not text_path.exists():
        return {"stem": metadata_path.stem, "status": "skipped", "reason": "missing text body"}

    subject = str(payload.get("subject") or "JVT Technologies").strip()
    body = text_path.read_text(encoding="utf-8", errors="replace")
    site_url = str(payload.get("site_url") or DEFAULT_SITE_URL)
    packet_type = packet_type_for(payload)
    result = rewrite_email(payload, packet_type=packet_type, subject=subject, body=body, site_url=site_url)
    report = {
        "stem": metadata_path.stem,
        "queue": metadata_path.parent.name,
        "packet_type": packet_type,
        "company_name": payload.get("company_name"),
        "recipient_email": payload.get("recipient_email") or payload.get("public_email"),
        "old_subject": subject,
        "rewritten": bool(result.get("rewritten")),
        "new_subject": result.get("subject") if result.get("rewritten") else result.get("candidate_subject"),
        "score": result.get("score"),
        "reason": result.get("reason") or result.get("validation_reasons") or result.get("reason"),
        "model": result.get("model"),
        "backend": result.get("backend"),
        "host": result.get("host"),
        "status": "rewritten" if result.get("rewritten") else "held",
    }
    if not result.get("rewritten"):
        return report
    new_subject = str(result.get("subject") or subject).strip()
    new_body = str(result.get("body") or body).strip() + "\n"
    if not write:
        return {**report, "status": "would-rewrite"}

    html_path = metadata_path.with_suffix(".html")
    md_path = metadata_path.with_suffix(".md")
    reply_to_email = str(payload.get("reply_to_email") or DEFAULT_REPLY_TO)
    html_body = render_text_email_html(
        new_body,
        title=new_subject,
        preheader=f"A focused JVT workflow note for {payload.get('company_name') or 'your team'}.",
        site_url=site_url,
        reply_to_email=reply_to_email,
    )
    text_path.write_text(new_body, encoding="utf-8")
    html_path.write_text(html_body + "\n", encoding="utf-8")
    rewrite_markdown(md_path, new_subject, new_body)
    payload["subject"] = new_subject
    payload["copy_voice"] = "model-copywriter-v1"
    payload["copywriter_result"] = {
        key: value
        for key, value in result.items()
        if key not in {"response", "body", "candidate_body"}
    }
    payload["copy_updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["email_theme"] = "jvt-dark-green-gold-graphite-v2"
    payload["email_theme_updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["html_path"] = str(html_path)
    payload["text_path"] = str(text_path)
    payload["review_path"] = str(md_path)
    write_json(metadata_path, payload)
    return report


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# JVT Agentic Copywriter",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Mode: `{report.get('mode')}`",
        f"- Queues: `{', '.join(report.get('queues') or [])}`",
        f"- Rewritten: `{report.get('rewritten_count')}/{report.get('result_count')}`",
        f"- Safety: {report.get('safety_boundary')}",
        "",
        "## Results",
        "",
    ]
    for item in report.get("results") or []:
        reason = item.get("reason")
        if isinstance(reason, list):
            reason = "; ".join(str(part) for part in reason)
        lines.append(
            f"- `{item.get('status')}` {item.get('stem')}: {item.get('old_subject')} -> {item.get('new_subject') or 'unchanged'}"
            f" (score={item.get('score')}, reason={reason or 'n/a'})"
        )
    if not report.get("results"):
        lines.append("- No eligible packets found.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Use the local model copywriter to rewrite staged unsent JVT outreach packets.")
    parser.add_argument("--queue", action="append", choices=["draft", "review", "approved"], default=[])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--include-initial", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--rewrite-existing", action="store_true", help="Rewrite packets that already have model-copywriter-v1 copy.")
    parser.add_argument("--exit-zero-on-held", action="store_true", help="Return success even when some packets are held by the copywriter gate.")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()

    queue_names = args.queue or ["review"]
    results: list[dict[str, Any]] = []
    for queue in queue_names:
        directory = args.root / "outreach" / "queue" / queue
        for metadata_path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime):
            payload = load_json(metadata_path)
            if not payload:
                continue
            if not args.include_initial and not is_followup(payload):
                continue
            if not args.rewrite_existing and payload.get("copy_voice") == "model-copywriter-v1":
                continue
            results.append(update_packet(metadata_path, write=args.write))
            if len(results) >= args.limit:
                break
        if len(results) >= args.limit:
            break

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "write" if args.write else "dry-run",
        "queues": queue_names,
        "limit": args.limit,
        "include_initial": args.include_initial,
        "result_count": len(results),
        "rewritten_count": sum(1 for item in results if item.get("status") in {"rewritten", "would-rewrite"}),
        "results": results,
        "safety_boundary": "Rewrites staged unsent outreach packets only. It does not approve, send, or follow up with active inbox hits.",
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-agentic-rewrite.json"
    latest_path = REPORT_DIR / "latest-agentic-rewrite.json"
    latest_markdown_path = REPORT_DIR / "latest-agentic-rewrite.md"
    write_json(report_path, report)
    write_json(latest_path, report)
    write_markdown_report(report, latest_markdown_path)
    print(json.dumps({"report_path": str(report_path), "rewritten_count": report["rewritten_count"], "result_count": len(results)}, indent=2))
    if any(item.get("status") == "held" for item in results) and not args.exit_zero_on_held:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
