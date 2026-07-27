#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("public_conversion_kv_sync.py")
SPEC = importlib.util.spec_from_file_location("public_conversion_kv_sync", MODULE_PATH)
assert SPEC and SPEC.loader
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


class MemoryKVClient:
    def __init__(self, records: dict[str, object]):
        self.records = records

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self.records if key.startswith(prefix))

    def get_json(self, key: str) -> dict:
        payload = self.records[key]
        if isinstance(payload, BaseException):
            raise payload
        return payload


class PublicConversionKVSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.checkpoint = root / "state" / "checkpoint.json"
        self.report_json = root / "state" / "latest.json"
        self.report_md = root / "state" / "latest.md"
        self.data_root = root / "data"
        self.inbox_root = root / "inbox"
        self.db_path = root / "ops.sqlite3"
        self.patches = [
            mock.patch.object(SYNC.intake, "DATA_ROOT", self.data_root),
            mock.patch.object(SYNC.intake, "SUBMISSION_ROOT", self.data_root / "submissions"),
            mock.patch.object(SYNC.intake, "EVENT_ROOT", self.data_root / "events"),
            mock.patch.object(SYNC.intake, "DEDUP_INDEX", self.data_root / "dedupe-index.json"),
            mock.patch.object(SYNC.intake, "EVENT_LOG", self.data_root / "events.jsonl"),
            mock.patch.object(SYNC.intake, "REPORT_JSON", root / "state" / "intake.json"),
            mock.patch.object(SYNC.intake, "REPORT_MD", root / "state" / "intake.md"),
            mock.patch.object(SYNC.intake, "OPS_DB", self.db_path),
            mock.patch.object(SYNC.intake, "INBOX_HANDOFF_ROOT", self.inbox_root),
            mock.patch.object(SYNC.intake, "refresh_pipeline_reports"),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tempdir.cleanup()

    def submission(self) -> dict:
        return {
            "submission_id": "wfintake_20260727_kv_alpha",
            "created_at": "2026-07-27T20:00:00+00:00",
            "contact": {
                "name": "Avery Morgan",
                "email": "avery@rivercitydentalops.com",
                "company": "River City Dental Ops",
            },
            "service_slug": "ai-voice-intake",
            "problem_description": (
                "We miss after-hours calls and need a callback packet that tells the team "
                "who called, what they need, and what should be reviewed first."
            ),
            "preferred_next_step": "email",
            "attribution": {"utm_source": "public-site"},
        }

    def records(self) -> dict[str, dict]:
        submission = self.submission()
        submission_id = submission["submission_id"]
        event = {
            "submission_id": submission_id,
            "event_type": "view",
            "created_at": "2026-07-27T19:59:00+00:00",
            "attribution": {"utm_source": "public-site"},
        }
        return {
            f"event:view:{submission_id}": event,
            f"submission:{submission_id}": submission,
        }

    def run_sync(self, client: MemoryKVClient, **kwargs) -> dict:
        return SYNC.sync_records(
            client,
            checkpoint_path=self.checkpoint,
            report_json=self.report_json,
            report_md=self.report_md,
            refresh_reports=True,
            **kwargs,
        )

    def test_imports_events_and_submission_exactly_once(self) -> None:
        client = MemoryKVClient(self.records())

        first = self.run_sync(client)
        second = self.run_sync(client)

        self.assertTrue(first["ok"])
        self.assertEqual(first["imported_submission_count"], 1)
        self.assertEqual(first["imported_event_count"], 1)
        self.assertEqual(first["unreconciled_count"], 0)
        self.assertEqual(second["attempted_count"], 0)
        self.assertEqual(len(list(self.inbox_root.glob("**/*.json"))), 1)
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0], 1)
        conn.close()

    def test_failed_record_is_not_checkpointed_and_retries(self) -> None:
        records = self.records()
        submission_key = next(key for key in records if key.startswith("submission:"))
        records[submission_key] = RuntimeError("temporary read failure for person@example.org token=abc")
        client = MemoryKVClient(records)

        first = self.run_sync(client)
        second = self.run_sync(client)

        self.assertFalse(first["ok"])
        self.assertEqual(first["unreconciled_count"], 1)
        self.assertEqual(second["attempted_count"], 1)
        serialized = self.report_json.read_text(encoding="utf-8")
        self.assertNotIn("person@example.org", serialized)
        self.assertNotIn("token=abc", serialized)

    def test_mismatched_key_and_submission_id_is_rejected(self) -> None:
        records = self.records()
        payload = self.submission()
        records["submission:wfintake_20260727_other"] = payload
        client = MemoryKVClient(records)

        report = self.run_sync(client)

        self.assertFalse(report["ok"])
        self.assertEqual(report["failed_count"], 1)
        self.assertEqual(report["unreconciled_count"], 1)

    def test_dry_run_does_not_checkpoint_or_write_pipeline(self) -> None:
        report = self.run_sync(MemoryKVClient(self.records()), dry_run=True)

        self.assertTrue(report["ok"])
        self.assertFalse(self.checkpoint.exists())
        self.assertEqual(report["unreconciled_count"], 2)
        self.assertFalse(self.db_path.exists())
        self.assertEqual(list(self.inbox_root.glob("**/*.json")), [])


if __name__ == "__main__":
    unittest.main()
