#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path, schema_path: Path) -> None:
    conn = connect(db_path)
    with schema_path.open("r", encoding="utf-8") as handle:
        conn.executescript(handle.read())
    conn.commit()
    conn.close()


def import_csv(db_path: Path, csv_path: Path) -> None:
    conn = connect(db_path)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            conn.execute(
                """
                INSERT OR REPLACE INTO leads (
                  id, company_name, website, city_state, industry, practice_area,
                  contact_page, public_email, notes, fit_score, outreach_status,
                  follow_up_status, last_touched_date, updated_at
                ) VALUES (
                  COALESCE((SELECT id FROM leads WHERE company_name = ? AND website = ?), NULL),
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
                )
                """,
                (
                    row["company_name"],
                    row["website"],
                    row["company_name"],
                    row["website"],
                    row["city_state"],
                    row["industry"],
                    row["practice_area"],
                    row["contact_page"],
                    row["public_email"],
                    row["notes"],
                    int(row["fit_score"] or 0),
                    row["outreach_status"] or "new",
                    row["follow_up_status"] or "none",
                    row["last_touched_date"] or None,
                ),
            )
    conn.commit()
    conn.close()


def list_leads(db_path: Path) -> None:
    conn = connect(db_path)
    rows = conn.execute(
        """
        SELECT id, company_name, city_state, practice_area, fit_score, outreach_status, follow_up_status
        FROM leads
        ORDER BY fit_score DESC, company_name ASC
        """
    ).fetchall()
    for row in rows:
        print(
            f"{row['id']:>3} | {row['company_name']:<32} | {row['city_state'] or '-':<18} | "
            f"{row['practice_area'] or '-':<20} | fit={row['fit_score']:<3} | "
            f"{row['outreach_status']}/{row['follow_up_status']}"
        )
    conn.close()


def show_lead(db_path: Path, lead_id: int) -> None:
    conn = connect(db_path)
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not row:
      raise SystemExit(f"Lead {lead_id} not found")
    for key in row.keys():
        print(f"{key}: {row[key]}")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-first JVT lead pipeline helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db")
    init_parser.add_argument("--db", required=True, type=Path)
    init_parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "schema.sql",
    )

    import_parser = subparsers.add_parser("import-csv")
    import_parser.add_argument("--db", required=True, type=Path)
    import_parser.add_argument("--csv", required=True, type=Path)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--db", required=True, type=Path)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--db", required=True, type=Path)
    show_parser.add_argument("--id", required=True, type=int)

    args = parser.parse_args()

    if args.command == "init-db":
        init_db(args.db, args.schema)
    elif args.command == "import-csv":
        import_csv(args.db, args.csv)
    elif args.command == "list":
        list_leads(args.db)
    elif args.command == "show":
        show_lead(args.db, args.id)


if __name__ == "__main__":
    main()
