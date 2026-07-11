#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipient_quality import evidence_gate, lead_payload


ROOT = Path("/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies")
DEFAULT_DB = ROOT / "lead-pipeline/data/jvt_leads.sqlite3"
DEFAULT_TEMPLATE = ROOT / "outreach/templates/initial-introduction.md"
DEFAULT_OUTPUT_DIR = ROOT / "outreach/queue/review"
DEFAULT_SCHEDULE_DIR = ROOT / "outreach/schedules"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BAD_EMAIL_FRAGMENTS = ("example@", "example.com", "domain.com", "test@", "placeholder")
GENERIC_COMPANY_NAMES = {
    "main office",
    "contact us",
    "contact",
    "home",
    "home page",
    "cpa websites",
    "tax preparation",
    "accounting and advisory firm",
    "a premier small business focused cpa firm",
}
GENERIC_COMPANY_PATTERNS = (
    re.compile(r"^about\s+", re.IGNORECASE),
    re.compile(r"^home\s+page$", re.IGNORECASE),
    re.compile(r"\b(company|agency)\s+in\s+[a-z ]+$", re.IGNORECASE),
    re.compile(r"\b(company|agency|firm)\s+[a-z .'-]+\s+(?:[a-z]{2}|[a-z]+)$", re.IGNORECASE),
    re.compile(r"^[a-z .'-]+,\s[A-Z]{2}\s+(accounting|cpa|law|property management)\b", re.IGNORECASE),
    re.compile(r"^contact\b.*\b(get\s+in\s+touch|contact\s+us)\b", re.IGNORECASE),
    re.compile(r"\bcpa\s+websites\b", re.IGNORECASE),
    re.compile(r"\b(management\s+software|software\s+platform|saas)\b", re.IGNORECASE),
    re.compile(r"\bresume\s+writing\b", re.IGNORECASE),
    re.compile(r"^professional\s+staffing\s+agency$", re.IGNORECASE),
    re.compile(r"^temporary\s+employment\s+services\s+&\s+staffing\s+agency$", re.IGNORECASE),
    re.compile(r"^jobs\s+and\s+staffing\s+solutions\b", re.IGNORECASE),
    re.compile(r"^title\s+company\s+", re.IGNORECASE),
    re.compile(r"^a\s+full\s+service\s+certified\s+public\s+accounting\s+firm$", re.IGNORECASE),
    re.compile(r"^a\s+premier\s+small\s+business\s+focused\s+cpa\s+firm$", re.IGNORECASE),
    re.compile(r"^accounting\s+and\s+advisory\s+firm$", re.IGNORECASE),
    re.compile(r"^expert\s+cpa\s+firm\b", re.IGNORECASE),
    re.compile(r"^virtual\s+cpa\s+accountant$", re.IGNORECASE),
    re.compile(r"^certified\s+public\s+accounting\s+firm$", re.IGNORECASE),
    re.compile(r"^tax\s+preparation$", re.IGNORECASE),
    re.compile(r"^parents\s+estate\s+planning\s+law\s+firm$", re.IGNORECASE),
    re.compile(r"^cpa\s+firm\s+[a-z .'-]+$", re.IGNORECASE),
    re.compile(r"^[a-z .'-]+\s+cpa\s+firm$", re.IGNORECASE),
    re.compile(r"^trusted\s+accounting\s+firm\s+for\s+business\b", re.IGNORECASE),
    re.compile(r"^accounting\s*&\s*consulting\s+firm\s+in\s+[a-z ,.]+$", re.IGNORECASE),
    re.compile(r"^[a-z ,.]+\s+(accounting|consulting|cpa)\s+firm$", re.IGNORECASE),
    re.compile(r"^[a-z .'-]+\s+(?:[a-z]{2}|[a-z]+)\s+cpa\s*&\s*accountant$", re.IGNORECASE),
    re.compile(r"^bookkeeping\s+services\s+in\s+[a-z ,]+", re.IGNORECASE),
    re.compile(r"\b(home|about|contact)\s+[-|]\s+", re.IGNORECASE),
)
BIG_ENTERPRISE_TERMS = (
    "skadden",
    "kirkland",
    "latham",
    "cravath",
    "wachtell",
    "sullivan & cromwell",
    "sullivan cromwell",
    "davis polk",
    "simpson thacher",
    "paul weiss",
    "white & case",
    "freshfields",
    "morgan lewis",
    "greenberg traurig",
    "deloitte",
    "pricewaterhousecoopers",
    "pwc",
    "ernst & young",
    "ey",
    "kpmg",
    "express employment",
)


def valid_email(value: str) -> bool:
    email = value.strip()
    if not email or not EMAIL_RE.match(email):
        return False
    lowered = email.lower()
    return not any(fragment in lowered for fragment in BAD_EMAIL_FRAGMENTS)


def root_domain(host: str) -> str:
    clean = host.lower().removeprefix("www.").split(":", 1)[0]
    parts = [part for part in clean.split(".") if part]
    if len(parts) < 2:
        return clean
    return ".".join(parts[-2:])


def email_matches_website(public_email: str, website: str) -> bool:
    if "@" not in public_email or not website:
        return False
    email_domain = public_email.rsplit("@", 1)[1].lower()
    match = re.search(r"https?://([^/]+)", website.lower())
    website_domain = match.group(1) if match else website.lower()
    return root_domain(email_domain) == root_domain(website_domain)


def queued_lead_ids(queue_root: Path) -> set[int]:
    queued: set[int] = set()
    for state in ("draft", "review", "approved", "sent", "replied"):
        for metadata_path in (queue_root / state).glob("*.json"):
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            lead_id = payload.get("lead_id")
            if isinstance(lead_id, int):
                queued.add(lead_id)
    return queued


def lead_rejection_reasons(row: sqlite3.Row, skip_ids: set[int], min_fit_score: int, allow_enterprise: bool) -> list[str]:
    reasons: list[str] = []
    company_name = (row["company_name"] or "").strip()
    public_email = (row["public_email"] or "").strip()
    website = (row["website"] or "").strip()
    practice_area = (row["practice_area"] or "").strip()
    city_state = (row["city_state"] or "").strip().lower()
    notes = (row["notes"] or "").strip().lower()
    company_lower = company_name.lower()
    fit_score = int(row["fit_score"] or 0)

    if row["id"] in skip_ids:
        reasons.append("already queued or previously sent")
    if (
        not company_name
        or company_lower in GENERIC_COMPANY_NAMES
        or any(pattern.search(company_name) for pattern in GENERIC_COMPANY_PATTERNS)
    ):
        reasons.append("generic or missing company name")
    if not valid_email(public_email):
        reasons.append("invalid or placeholder email")
    elif not email_matches_website(public_email, website):
        reasons.append("email domain does not match website")
    if fit_score < min_fit_score:
        reasons.append(f"fit score below {min_fit_score}")
    if not practice_area:
        reasons.append("missing practice area for personalization")
    if city_state and any(term in city_state for term in ("catholic church", " is a ", " is the ")):
        reasons.append("polluted location text")
    if "fictional" in notes:
        reasons.append("fictional/test lead")
    if not allow_enterprise and any(term in company_lower for term in BIG_ENTERPRISE_TERMS):
        reasons.append("too enterprise/big-firm for early outreach")
    evidence_reasons, _ = evidence_gate(lead_payload(row))
    reasons.extend(f"recipient_quality:{reason}" for reason in evidence_reasons)
    return reasons


def recipient_evidence_for_row(row: sqlite3.Row) -> dict[str, object]:
    _, evidence = evidence_gate(lead_payload(row))
    return evidence


def select_leads(
    db_path: Path,
    queue_root: Path,
    limit: int,
    min_fit_score: int,
    allow_enterprise: bool,
) -> tuple[list[sqlite3.Row], list[dict[str, object]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    skip_ids = queued_lead_ids(queue_root)
    rows = conn.execute(
        """
        SELECT *
        FROM leads
        WHERE outreach_status = 'new'
        ORDER BY fit_score DESC, id ASC
        """
    ).fetchall()
    conn.close()

    selected: list[sqlite3.Row] = []
    rejected: list[dict[str, object]] = []
    for row in rows:
        reasons = lead_rejection_reasons(row, skip_ids, min_fit_score, allow_enterprise)
        if reasons:
            rejected.append(
                {
                    "lead_id": row["id"],
                    "company_name": row["company_name"],
                    "recipient_email": row["public_email"],
                    "fit_score": row["fit_score"],
                    "practice_area": row["practice_area"],
                    "reasons": reasons,
                }
            )
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected, rejected


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "draft"


def packet_stem(packet_date: str, company_name: str, template_path: Path) -> str:
    return f"{packet_date}-{slugify(company_name)}-{template_path.stem}"


def run_generate_draft(
    root: Path,
    db_path: Path,
    template_path: Path,
    output_dir: Path,
    lead_id: int,
    packet_date: str,
    contact_name: str,
    reply_to_email: str,
    site_url: str,
    sender_name: str,
    sender_title: str,
    sender_company: str,
) -> None:
    subprocess.run(
        [
            "python3",
            str(root / "outreach/tools/generate_draft.py"),
            "--db",
            str(db_path),
            "--lead-id",
            str(lead_id),
            "--template",
            str(template_path),
            "--output-dir",
            str(output_dir),
            "--contact-name",
            contact_name,
            "--reply-to-email",
            reply_to_email,
            "--site-url",
            site_url,
            "--sender-name",
            sender_name,
            "--sender-title",
            sender_title,
            "--sender-company",
            sender_company,
            "--packet-date",
            packet_date,
        ],
        check=True,
    )


def write_schedule_files(
    schedule_dir: Path,
    packet_date: str,
    stems: list[str],
    rows: list[sqlite3.Row],
    rejected: list[dict[str, object]],
    min_fit_score: int,
) -> None:
    schedule_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{packet_date}-daily-wave"
    batches = [stems[index : index + 5] for index in range(0, len(stems), 5)]
    target_times = ["09:05", "10:40", "13:15"]
    send_windows = [
        {"target_time": target_times[index] if index < len(target_times) else "manual", "stems": batch}
        for index, batch in enumerate(batches)
    ]
    payload = {
        "name": "JVT Technologies QA-filtered daily outreach wave",
        "status": "pending_operator_confirmation",
        "scheduled_date": packet_date,
        "timezone": "America/New_York",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "qa_policy": {
            "min_fit_score": min_fit_score,
            "requires_valid_email": True,
            "requires_practice_area": True,
            "requires_recipient_evidence_pass": True,
            "excludes_already_queued_or_sent": True,
            "excludes_fictional_test_leads": True,
            "excludes_big_enterprise_targets": True,
        },
        "send_windows": send_windows,
        "guardrails": [
            "No autonomous prospect send is enabled.",
            "Packets stay in review until the operator approves the wave in the dashboard.",
            "Sending requires a final dashboard confirmation.",
        ],
        "excluded_candidates": rejected[:30],
        "selected_leads": [
            {
                "lead_id": row["id"],
                "company_name": row["company_name"],
                "recipient_email": row["public_email"],
                "fit_score": row["fit_score"],
                "practice_area": row["practice_area"],
                "city_state": row["city_state"],
                "recipient_evidence": recipient_evidence_for_row(row),
            }
            for row in rows
        ],
    }
    (schedule_dir / f"{stem}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# JVT Technologies QA-Filtered Daily Outreach Wave",
        "",
        "Status: pending operator confirmation  ",
        f"Date: {packet_date}  ",
        "Timezone: America/New_York  ",
        "",
        "No automatic prospect send is enabled. Review in the dashboard, move the wave to approved, then confirm send.",
        "",
        "## QA Policy",
        "",
        f"- Minimum fit score: {min_fit_score}",
        "- Requires valid non-placeholder email",
        "- Requires practice-area metadata for personalization",
        "- Requires shared recipient-evidence pass before packet generation",
        "- Excludes already queued or previously sent leads",
        "- Excludes fictional/test leads",
        "- Excludes broad enterprise targets for early outreach",
        "",
        "## Selected Leads",
        "",
    ]
    for row in rows:
        md_lines.append(
            f"- {row['company_name']} - {row['public_email']} - fit {row['fit_score']} - {row['practice_area']}"
        )
    if rejected:
        md_lines.extend(["", "## Excluded Candidates", ""])
        for item in rejected[:30]:
            md_lines.append(
                f"- {item['company_name']} - fit {item['fit_score']} - {', '.join(item['reasons'])}"
            )
    md_lines.append("")
    (schedule_dir / f"{stem}.md").write_text("\n".join(md_lines), encoding="utf-8")

    script_path = schedule_dir / f"send-{stem}.sh"
    script_path.write_text(build_send_script(packet_date, send_windows), encoding="utf-8")
    script_path.chmod(0o755)


def build_send_script(packet_date: str, send_windows: list[dict[str, object]]) -> str:
    confirm_name = f"JVT_CONFIRM_SEND_{packet_date.replace('-', '_')}"
    batch_blocks: list[str] = []
    for index, window in enumerate(send_windows, start=1):
        stems = window["stems"]
        quoted = "\n  ".join(f'"{stem}"' for stem in stems)
        batch_blocks.append(f"BATCH_{index}=(\n  {quoted}\n)")

    run_lines: list[str] = []
    for index in range(1, len(send_windows) + 1):
        run_lines.append(f'run_batch "{index}" "${{BATCH_{index}[@]}}"')
        if index < len(send_windows):
            run_lines.append('echo "Waiting 90 minutes before next batch."')
            run_lines.append("sleep 5400")

    return f"""#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
OUTREACH_TOOLS="$ROOT/outreach/tools"
SEND_DATE="{packet_date}"
CONFIRM_FLAG="${{{confirm_name}:-}}"
LOCAL_ENV_FILE="$ROOT/outreach/.env.local"

if [ -f "$LOCAL_ENV_FILE" ]; then
  set -a
  source "$LOCAL_ENV_FILE"
  set +a
fi

PYTHON_BIN="${{JVT_PYTHON_BIN:-python3}}"

{chr(10).join(batch_blocks)}

move_to_approved_if_needed() {{
  local stem="$1"
  if [ -f "$ROOT/outreach/queue/approved/$stem.json" ]; then
    return 0
  fi
  if [ -f "$ROOT/outreach/queue/review/$stem.json" ]; then
    zsh "$OUTREACH_TOOLS/reviewed_outreach.sh" move "$stem" review approved
    return 0
  fi
  echo "Missing packet in review/approved: $stem" >&2
  return 1
}}

run_batch() {{
  local batch_name="$1"
  shift
  local stems=("$@")
  local send_args=()

  for stem in "${{stems[@]}}"; do
    move_to_approved_if_needed "$stem"
    send_args+=(--stem "$stem")
  done

  echo "Sending daily wave batch $batch_name (${{#stems[@]}} packets)."
  "$PYTHON_BIN" "$ROOT/outreach/tools/send_approved.py" \\
    --max-per-run "${{#stems[@]}}" \\
    --daily-limit 12 \\
    --delay-seconds 45 \\
    --send \\
    "${{send_args[@]}}"
}}

if [ "$CONFIRM_FLAG" != "yes" ]; then
  cat <<EOF
Dry-run only. Nothing was sent.

This script is guarded because it sends third-party prospect email.
To send this wave, run:

{confirm_name}=yes zsh outreach/schedules/send-{packet_date}-daily-wave.sh

Planned date: $SEND_DATE
EOF
  exit 2
fi

today="$(date +%F)"
if [[ "$today" < "$SEND_DATE" ]]; then
  echo "Refusing to send before $SEND_DATE. Today is $today." >&2
  exit 1
fi

cd "$ROOT"

{chr(10).join(run_lines)}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a personalized daily JVT outreach wave into review.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--schedule-dir", type=Path, default=DEFAULT_SCHEDULE_DIR)
    parser.add_argument("--packet-date", default=date.today().isoformat())
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--min-fit-score", type=int, default=85)
    parser.add_argument("--allow-enterprise", action="store_true")
    parser.add_argument("--contact-name", default="team")
    parser.add_argument("--reply-to-email", default="hello@jvt-technologies.com")
    parser.add_argument("--site-url", default="https://jvt-technologies.com")
    parser.add_argument("--sender-name", default="Chandru Vasudevan")
    parser.add_argument("--sender-title", default="Founder")
    parser.add_argument("--sender-company", default="JVT Technologies LLC")
    args = parser.parse_args()

    rows, rejected = select_leads(
        args.db,
        args.root / "outreach/queue",
        args.limit,
        args.min_fit_score,
        args.allow_enterprise,
    )
    if not rows:
        write_schedule_files(args.schedule_dir, args.packet_date, [], [], rejected, args.min_fit_score)
        print(
            json.dumps(
                {
                    "packet_date": args.packet_date,
                    "count": 0,
                    "stems": [],
                    "excluded_count": len(rejected),
                    "noop": True,
                    "message": "No eligible new leads with valid email addresses were found.",
                },
                indent=2,
            )
        )
        return

    stems = []
    for row in rows:
        run_generate_draft(
            args.root,
            args.db,
            args.template,
            args.output_dir,
            int(row["id"]),
            args.packet_date,
            args.contact_name,
            args.reply_to_email,
            args.site_url,
            args.sender_name,
            args.sender_title,
            args.sender_company,
        )
        stems.append(packet_stem(args.packet_date, row["company_name"], args.template))

    write_schedule_files(args.schedule_dir, args.packet_date, stems, rows, rejected, args.min_fit_score)
    print(
        json.dumps(
            {
                "packet_date": args.packet_date,
                "count": len(stems),
                "stems": stems,
                "excluded_count": len(rejected),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
