#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDNAMES = [
    "client_slug",
    "client_name",
    "pipeline_stage",
    "lead_id",
    "primary_contact_name",
    "primary_contact_email",
    "website",
    "service_line",
    "intake_date",
    "start_date",
    "last_activity_date",
    "workspace_path",
    "notes",
]


def ensure_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()


def read_rows(path: Path) -> list[dict[str, str]]:
    ensure_csv(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def upsert_row(path: Path, payload: dict[str, str]) -> None:
    rows = read_rows(path)
    existing = None
    for row in rows:
        if row["client_slug"] == payload["client_slug"]:
            existing = row
            break
    if existing is None:
        existing = {field: "" for field in FIELDNAMES}
        rows.append(existing)
    for key, value in payload.items():
        if value not in (None, ""):
            existing[key] = value
    write_rows(path, rows)


def list_rows(path: Path) -> None:
    rows = read_rows(path)
    for row in rows:
        print(
            " | ".join(
                [
                    row["client_slug"] or "-",
                    row["client_name"] or "-",
                    row["pipeline_stage"] or "-",
                    row["service_line"] or "-",
                    row["primary_contact_email"] or "-",
                ]
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain the local JVT client registry.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path.home() / "Documents" / "JVT-Technologies" / "00-admin" / "client-registry.csv",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    upsert = subparsers.add_parser("upsert")
    upsert.add_argument("--slug", required=True)
    upsert.add_argument("--name", required=True)
    upsert.add_argument("--pipeline-stage", default="intake")
    upsert.add_argument("--lead-id", default="")
    upsert.add_argument("--primary-contact-name", default="")
    upsert.add_argument("--primary-contact-email", default="")
    upsert.add_argument("--website", default="")
    upsert.add_argument("--service-line", default="")
    upsert.add_argument("--intake-date", default="")
    upsert.add_argument("--start-date", default="")
    upsert.add_argument("--last-activity-date", default="")
    upsert.add_argument("--workspace-path", default="")
    upsert.add_argument("--notes", default="")

    subparsers.add_parser("list")

    args = parser.parse_args()
    csv_path = args.csv.expanduser().resolve()

    if args.command == "upsert":
        payload = {
            "client_slug": args.slug,
            "client_name": args.name,
            "pipeline_stage": args.pipeline_stage,
            "lead_id": args.lead_id,
            "primary_contact_name": args.primary_contact_name,
            "primary_contact_email": args.primary_contact_email,
            "website": args.website,
            "service_line": args.service_line,
            "intake_date": args.intake_date,
            "start_date": args.start_date,
            "last_activity_date": args.last_activity_date,
            "workspace_path": args.workspace_path,
            "notes": args.notes,
        }
        upsert_row(csv_path, payload)
        print(f"Upserted {args.slug} in {csv_path}")
    elif args.command == "list":
        list_rows(csv_path)


if __name__ == "__main__":
    main()
