#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("public_conversion_intake.py")
SPEC = importlib.util.spec_from_file_location("public_conversion_intake", MODULE_PATH)
assert SPEC and SPEC.loader
INTAKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTAKE)


class PublicConversionIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db_path = root / "ops" / "jvt_ops.sqlite3"
        self.data_root = root / "data" / "public-conversion-intake"
        self.state_root = root / "state"
        self.inbox_root = root / "outreach" / "inbox" / "new" / "public-intake"
        self.queue_root = root / "outreach" / "queue"
        self.patches = [
            mock.patch.object(INTAKE, "DATA_ROOT", self.data_root),
            mock.patch.object(INTAKE, "SUBMISSION_ROOT", self.data_root / "submissions"),
            mock.patch.object(INTAKE, "EVENT_ROOT", self.data_root / "events"),
            mock.patch.object(INTAKE, "DEDUP_INDEX", self.data_root / "dedupe-index.json"),
            mock.patch.object(INTAKE, "EVENT_LOG", self.data_root / "events.jsonl"),
            mock.patch.object(INTAKE, "REPORT_JSON", self.state_root / "latest-public-conversion-intake.json"),
            mock.patch.object(INTAKE, "REPORT_MD", self.state_root / "latest-public-conversion-intake.md"),
            mock.patch.object(INTAKE, "OPS_DB", self.db_path),
            mock.patch.object(INTAKE, "INBOX_HANDOFF_ROOT", self.inbox_root),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tempdir.cleanup()

    def valid_payload(self, submission_id: str = "wfintake_20260727_alpha") -> dict[str, str]:
        return {
            "submission_id": submission_id,
            "name": "Avery Morgan",
            "public_business_email": "avery@rivercitydentalops.com",
            "company": "River City Dental Ops",
            "service_interest": "ai-voice-intake",
            "problem_description": (
                "We miss after-hours calls and need a safer callback packet that tells the team "
                "who called, what they need, and what must be reviewed first."
            ),
            "preferred_next_step": "email",
            "source_url": "https://jvt-technologies.com/?utm_source=linkedin&utm_campaign=workflow-intake",
            "page_path": "/",
        }

    def db_counts(self) -> dict[str, int]:
        conn = sqlite3.connect(self.db_path)
        rows = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("accounts", "contacts", "opportunities", "interactions")
        }
        outbound = conn.execute(
            "SELECT COUNT(*) FROM interactions WHERE channel='email' AND direction='outbound'"
        ).fetchone()[0]
        conn.close()
        rows["outbound_interactions"] = outbound
        return rows

    def test_valid_submission_creates_canonical_handoff_without_send(self) -> None:
        result = INTAKE.submit_payload(self.valid_payload(), refresh_existing_reports=False)
        metrics = INTAKE.build_metrics()

        self.assertTrue(result["ok"])
        self.assertTrue(result["qualified"])
        self.assertFalse(result["duplicate"])
        self.assertEqual(metrics["completed_submission_count"], 1)
        self.assertEqual(metrics["qualified_submission_count"], 1)
        self.assertEqual(metrics["opportunity_handoff_count"], 1)
        self.assertEqual(metrics["service_interest_counts"], {"ai-voice-intake": 1})
        self.assertEqual(self.db_counts()["opportunities"], 1)
        self.assertEqual(self.db_counts()["outbound_interactions"], 0)
        self.assertEqual(list(self.queue_root.glob("**/*")), [])
        self.assertEqual(len(list(self.inbox_root.glob("**/*.json"))), 1)

    def test_retry_with_same_submission_id_is_idempotent(self) -> None:
        first = INTAKE.submit_payload(self.valid_payload(), refresh_existing_reports=False)
        second = INTAKE.submit_payload(self.valid_payload(), refresh_existing_reports=False)

        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(INTAKE.build_metrics()["completed_submission_count"], 1)
        self.assertEqual(self.db_counts()["opportunities"], 1)

    def test_duplicate_submission_is_stored_but_excluded_from_conversion_metrics(self) -> None:
        first = self.valid_payload("wfintake_20260727_alpha")
        duplicate = self.valid_payload("wfintake_20260727_beta")
        INTAKE.submit_payload(first, refresh_existing_reports=False)
        result = INTAKE.submit_payload(duplicate, refresh_existing_reports=False)
        metrics = INTAKE.build_metrics()

        self.assertTrue(result["duplicate"])
        self.assertEqual(metrics["stored_submission_count"], 2)
        self.assertEqual(metrics["completed_submission_count"], 1)
        self.assertEqual(metrics["duplicate_submission_count"], 1)
        self.assertEqual(self.db_counts()["opportunities"], 1)

    def test_concurrent_identical_submissions_qualify_exactly_once(self) -> None:
        payloads = [
            self.valid_payload(f"wfintake_20260727_concurrent_{index:02d}")
            for index in range(8)
        ]

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda payload: INTAKE.submit_payload(payload, refresh_existing_reports=False),
                    payloads,
                )
            )

        self.assertEqual(sum(bool(result["qualified"]) for result in results), 1)
        self.assertEqual(sum(not bool(result["duplicate"]) for result in results), 1)
        self.assertEqual(INTAKE.build_metrics()["completed_submission_count"], 1)
        self.assertEqual(INTAKE.build_metrics()["duplicate_submission_count"], 7)
        self.assertEqual(self.db_counts()["accounts"], 1)
        self.assertEqual(self.db_counts()["opportunities"], 1)

    def test_existing_contact_email_reuses_canonical_account(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        INTAKE.jvt_ops_db.create_schema(conn)
        INTAKE.jvt_ops_db.upsert_services(conn)
        canonical_account_id = INTAKE.jvt_ops_db.get_or_create_account_values(
            conn,
            name="River City Dental",
            website="https://rivercitydentalops.com",
            industry="dental",
            source="lead-db",
        )
        canonical_contact_id = INTAKE.jvt_ops_db.get_or_create_contact(
            conn,
            canonical_account_id,
            "avery@rivercitydentalops.com",
            source="lead-db",
        )
        conn.commit()
        conn.close()

        payload = self.valid_payload()
        payload["company"] = "River City Dental Ops Intake Team"
        result = INTAKE.submit_payload(payload, refresh_existing_reports=False)

        conn = sqlite3.connect(self.db_path)
        account_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        opportunity_account_id = conn.execute(
            "SELECT account_id FROM opportunities WHERE id=?",
            (result["opportunity_id"],),
        ).fetchone()[0]
        contact_account_id = conn.execute(
            "SELECT account_id FROM contacts WHERE id=?",
            (canonical_contact_id,),
        ).fetchone()[0]
        conn.close()

        self.assertEqual(account_count, 1)
        self.assertEqual(opportunity_account_id, canonical_account_id)
        self.assertEqual(contact_account_id, canonical_account_id)

    def test_malformed_internal_and_placeholder_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(INTAKE.IntakeError, "valid public business email"):
            payload = self.valid_payload("wfintake_20260727_bad1")
            payload["public_business_email"] = "not-an-email"
            INTAKE.submit_payload(payload)

        with self.assertRaisesRegex(INTAKE.IntakeError, "non-JVT"):
            payload = self.valid_payload("wfintake_20260727_bad2")
            payload["public_business_email"] = "hello@jvt-technologies.com"
            INTAKE.submit_payload(payload)

        with self.assertRaisesRegex(INTAKE.IntakeError, "real public business"):
            payload = self.valid_payload("wfintake_20260727_bad3")
            payload["public_business_email"] = "test@example.com"
            INTAKE.submit_payload(payload)

    def test_sensitive_or_attachment_payloads_are_rejected(self) -> None:
        with self.assertRaisesRegex(INTAKE.IntakeError, "credentials"):
            payload = self.valid_payload("wfintake_20260727_sensitive")
            payload["problem_description"] += " The password is hunter2."
            INTAKE.submit_payload(payload)

        with self.assertRaisesRegex(INTAKE.IntakeError, "upload"):
            payload = self.valid_payload("wfintake_20260727_file")
            payload["attachments"] = ["workflow.pdf"]
            INTAKE.submit_payload(payload)

        with self.assertRaisesRegex(INTAKE.IntakeError, "payment data"):
            payload = self.valid_payload("wfintake_20260727_ssn")
            payload["problem_description"] += " A caller included 123-45-6789 in the notes."
            INTAKE.submit_payload(payload)

        with self.assertRaisesRegex(INTAKE.IntakeError, "payment data"):
            payload = self.valid_payload("wfintake_20260727_card")
            payload["problem_description"] += " A caller included 4111 1111 1111 1111 in the notes."
            INTAKE.submit_payload(payload)

    def test_ordinary_patient_appointment_language_is_allowed_and_raw_pii_is_not_retained(self) -> None:
        payload = self.valid_payload("wfintake_20260727_patient")
        payload["problem_description"] = (
            "We need help routing patient appointment calls after hours into a callback queue "
            "so the front desk can review the request the next morning."
        )
        payload["referrer"] = "https://search.example/results?q=Avery+Morgan"

        result = INTAKE.submit_payload(payload, refresh_existing_reports=False)
        stored = INTAKE.existing_submission(result["submission_id"])

        self.assertTrue(result["qualified"])
        self.assertNotIn("name", stored["contact"])
        self.assertNotIn("email", stored["contact"])
        self.assertNotIn("problem_description", stored)
        self.assertEqual(stored["contact"]["company"], "River City Dental Ops")
        self.assertEqual(stored["contact"]["email_domain"], "rivercitydentalops.com")
        self.assertEqual(stored["attribution"]["source_url"], "https://jvt-technologies.com/")
        self.assertNotIn("referrer", stored["attribution"])
        self.assertEqual(stored["pii_retention"]["raw_form_pii"], "discarded_after_canonical_handoff")

    def test_form_view_and_start_metrics_are_unique_by_submission_id(self) -> None:
        event_payload = {
            "submission_id": "wfintake_20260727_event",
            "source_url": "https://jvt-technologies.com/?utm_source=organic",
        }
        INTAKE.record_client_event(event_payload, "view")
        INTAKE.record_client_event(event_payload, "view")
        INTAKE.record_client_event(event_payload, "start")

        metrics = INTAKE.build_metrics()
        self.assertEqual(metrics["form_view_count"], 1)
        self.assertEqual(metrics["form_start_count"], 1)

    def test_worker_record_shape_can_be_reconciled_from_export(self) -> None:
        payload = self.valid_payload("wfintake_20260727_worker_export")
        worker_record = {
            "submission_id": payload["submission_id"],
            "contact": {
                "name": payload["name"],
                "email": payload["public_business_email"],
                "company": payload["company"],
            },
            "service_slug": payload["service_interest"],
            "problem_description": payload["problem_description"],
            "preferred_next_step": payload["preferred_next_step"],
            "attribution": {"utm_source": "kv-export", "source_url": payload["source_url"]},
        }

        result = INTAKE.submit_payload(worker_record, refresh_existing_reports=False)

        self.assertTrue(result["qualified"])
        self.assertEqual(INTAKE.build_metrics()["source_counts"], {"kv-export": 1})
        self.assertEqual(self.db_counts()["opportunities"], 1)


if __name__ == "__main__":
    unittest.main()
