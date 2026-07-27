#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("prepare_fresh_research_packets.py")
SPEC = importlib.util.spec_from_file_location("prepare_fresh_research_packets", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FreshLeadPacketPrepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for queue in ("draft", "review", "approved", "sent", "replied"):
            (self.root / "outreach" / "queue" / queue).mkdir(parents=True, exist_ok=True)
        (self.root / "ops" / "agent-control" / "state").mkdir(parents=True)
        self.db = self.root / "leads.sqlite3"
        conn = sqlite3.connect(self.db)
        conn.execute(
            """
            CREATE TABLE leads (
                id INTEGER PRIMARY KEY,
                company_name TEXT,
                public_email TEXT,
                website TEXT,
                contact_page TEXT,
                industry TEXT,
                practice_area TEXT,
                city_state TEXT,
                notes TEXT,
                fit_score INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO leads
            (id, company_name, public_email, website, contact_page, industry, practice_area, city_state, notes, fit_score)
            VALUES
            (1, 'Example Elder Law, PLLC', 'hello@exampleelderlaw.com',
             'https://exampleelderlaw.com', 'https://exampleelderlaw.com/contact',
             'Law Firm', 'Elder Law', 'Trenton, NJ',
             'Public firm contact for document-heavy elder-law intake and planning workflows.', 95)
            """
        )
        conn.commit()
        conn.close()
        self.status = self.root / "research.json"
        self.status.write_text(
            json.dumps(
                {
                    "generated_at": "2026-07-27T01:00:00+00:00",
                    "new_leads_added": 1,
                    "new_leads": [
                        {
                            "company_name": "Example Elder Law, PLLC",
                            "website": "https://exampleelderlaw.com",
                        }
                    ],
                }
            )
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_dry_run_selects_new_qualified_lead(self) -> None:
        report = MODULE.prepare_packets(
            root=self.root,
            status_path=self.status,
            db_path=self.db,
            max_packets=5,
            min_fit_score=85,
            dry_run=True,
        )

        self.assertEqual(report["staged_count"], 1)
        self.assertEqual(report["staged"][0]["decision"], "would_stage")
        self.assertEqual(report["source_research_generated_at"], "2026-07-27T01:00:00+00:00")

    def test_dry_run_skips_already_queued_lead(self) -> None:
        queued = self.root / "outreach" / "queue" / "review" / "existing.json"
        queued.write_text(json.dumps({"lead_id": 1}))

        report = MODULE.prepare_packets(
            root=self.root,
            status_path=self.status,
            db_path=self.db,
            max_packets=5,
            min_fit_score=85,
            dry_run=True,
        )

        self.assertEqual(report["staged_count"], 0)
        self.assertEqual(report["skipped_count"], 1)
        self.assertIn("already queued or previously sent", report["skipped"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
