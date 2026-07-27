#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sqlite3
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("jvt_ops_db.py")
SPEC = importlib.util.spec_from_file_location("jvt_ops_db", MODULE_PATH)
assert SPEC and SPEC.loader
OPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPS)


class JvtOpsDbTests(unittest.TestCase):
    def test_document_reply_is_not_misclassified_from_phone_signature(self) -> None:
        payload = {
            "subject": "Re: A practical document workflow idea for Farr Law Firm",
            "snippet": "Ok. Evan Farr, Attorney. Fairfax Tel: 703-555-0100. Sent from my phone.",
        }

        self.assertEqual(OPS.infer_service_slug_from_inbox(payload), "private-doc-intel")

    def test_explicit_voice_subject_wins(self) -> None:
        payload = {
            "subject": "Re: AI receptionist pilot",
            "snippet": "We want after-hours call intake for our office.",
        }

        self.assertEqual(OPS.infer_service_slug_from_inbox(payload), "ai-voice-intake")

    def test_explicit_public_intake_service_slug_wins(self) -> None:
        payload = {
            "service_slug": "meeting-to-action",
            "subject": "Public workflow intake: documents",
            "snippet": "We need cleaner document and meeting handoffs.",
        }

        self.assertEqual(OPS.infer_service_slug_from_inbox(payload), "meeting-to-action")

    def test_schema_contains_commercial_ledger(self) -> None:
        conn = sqlite3.connect(":memory:")
        OPS.create_schema(conn)
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        self.assertIn("opportunity_commercial", names)


if __name__ == "__main__":
    unittest.main()
