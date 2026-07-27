#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("conversion_pipeline.py")
SPEC = importlib.util.spec_from_file_location("conversion_pipeline", MODULE_PATH)
assert SPEC and SPEC.loader
PIPELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PIPELINE)


class ConversionPipelineTests(unittest.TestCase):
    def test_warm_opportunity_gets_value_and_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "ops.sqlite3"
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            PIPELINE.jvt_ops_db.create_schema(conn)
            now = PIPELINE.utc_now()
            conn.execute(
                "INSERT INTO service_catalog VALUES(?, ?, ?, ?, ?)",
                ("private-doc-intel", "Private docs", "", "pilot", now),
            )
            conn.execute(
                "INSERT INTO accounts(name, website, industry, city_state, source, created_at, updated_at) VALUES(?, '', '', '', 'test', ?, ?)",
                ("Farr Law Firm", now, now),
            )
            account_id = conn.execute("SELECT id FROM accounts").fetchone()[0]
            conn.execute(
                "INSERT INTO opportunities(account_id, service_slug, stage, source, notes, created_at, updated_at) VALUES(?, ?, ?, '', '', ?, ?)",
                (account_id, "private-doc-intel", "reply-sent-awaiting-next", now, now),
            )
            opportunity_id = conn.execute("SELECT id FROM opportunities").fetchone()[0]
            conn.commit()
            item = {
                "id": opportunity_id,
                "account_name": "Farr Law Firm",
                "service_slug": "private-doc-intel",
                "service_name": "Private docs",
                "stage": "reply-sent-awaiting-next",
                "source": "",
                "updated_at": now,
            }
            with mock.patch.object(PIPELINE, "REPO_ROOT", Path(temp)):
                result = PIPELINE.upsert_commercial(conn, item)

        self.assertEqual(result["pipeline_stage"], "warm")
        self.assertEqual(result["estimated_value_low"], 1500.0)
        self.assertEqual(result["weighted_value"], 650.0)
        self.assertIn("generic no-reply", result["next_action"])

    def test_manual_stage_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "ops.sqlite3"
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            PIPELINE.jvt_ops_db.create_schema(conn)
            now = PIPELINE.utc_now()
            conn.execute("INSERT INTO service_catalog VALUES('workflow-automation', 'Workflow', '', 'pilot', ?)", (now,))
            conn.execute(
                "INSERT INTO accounts(name, website, industry, city_state, source, created_at, updated_at) VALUES('BITS', '', '', '', 'test', ?, ?)",
                (now, now),
            )
            account_id = conn.execute("SELECT id FROM accounts").fetchone()[0]
            conn.execute(
                "INSERT INTO opportunities(account_id, service_slug, stage, source, notes, created_at, updated_at) VALUES(?, 'workflow-automation', 'active', '', '', ?, ?)",
                (account_id, now, now),
            )
            opportunity_id = conn.execute("SELECT id FROM opportunities").fetchone()[0]
            conn.execute(
                """
                INSERT INTO opportunity_commercial(
                  opportunity_id, pipeline_stage, estimated_value_low, estimated_value_high, probability,
                  weighted_value, cash_collected, stage_source, created_at, updated_at
                ) VALUES(?, 'proposal', 1000, 2000, .5, 750, 100, 'manual', ?, ?)
                """,
                (opportunity_id, now, now),
            )
            conn.commit()
            item = {
                "id": opportunity_id,
                "account_name": "BITS",
                "service_slug": "workflow-automation",
                "stage": "active",
                "source": "",
                "updated_at": now,
            }
            with mock.patch.object(PIPELINE, "REPO_ROOT", Path(temp)):
                result = PIPELINE.upsert_commercial(conn, item)

        self.assertEqual(result["pipeline_stage"], "proposal")
        self.assertEqual(result["cash_collected"], 100.0)
        self.assertEqual(result["stage_source"], "manual")


if __name__ == "__main__":
    unittest.main()
