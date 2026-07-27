#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("reconcile_replies.py")
SPEC = importlib.util.spec_from_file_location("reconcile_replies", MODULE_PATH)
assert SPEC and SPEC.loader
RECONCILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECONCILE)


class ReplyReconciliationTests(unittest.TestCase):
    def test_moves_latest_matching_sent_packet_to_replied(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            queue = root / "outreach" / "queue"
            inbox = root / "outreach" / "inbox"
            state = root / "state"
            for bucket in ("sent", "replied"):
                (queue / bucket).mkdir(parents=True)
            reviewed = inbox / "reviewed" / "2026-01-01"
            reviewed.mkdir(parents=True)
            initial = {
                "recipient_email": "owner@example.com",
                "subject": "A practical workflow idea",
                "sent_at": "2026-01-01T10:00:00+00:00",
                "status": "sent",
            }
            followup = {**initial, "sent_at": "2026-01-02T10:00:00+00:00"}
            (queue / "sent" / "initial.json").write_text(json.dumps(initial), encoding="utf-8")
            (queue / "sent" / "followup.json").write_text(json.dumps(followup), encoding="utf-8")
            reply_path = reviewed / "reply.json"
            reply_path.write_text(
                json.dumps(
                    {
                        "from": "Owner <owner@example.com>",
                        "subject": "Re: A practical workflow idea",
                        "triage_bucket": "direct",
                        "triage_priority": "high",
                        "triage_action": "review",
                        "captured_at": "2026-01-03T10:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(RECONCILE, "QUEUE_ROOT", queue),
                mock.patch.object(RECONCILE, "INBOX_ROOT", inbox),
                mock.patch.object(RECONCILE, "REPORT_JSON", state / "latest.json"),
                mock.patch.object(RECONCILE, "REPORT_MD", state / "latest.md"),
            ):
                report = RECONCILE.reconcile()

            self.assertEqual(report["matched_count"], 1)
            self.assertTrue((queue / "replied" / "followup.json").exists())
            self.assertTrue((queue / "sent" / "initial.json").exists())
            self.assertFalse((queue / "sent" / "followup.json").exists())

    def test_system_mail_is_not_reconciled(self) -> None:
        payload = {
            "from": "Alerts <noreply@bankofamerica.com>",
            "subject": "Re: A practical workflow idea",
            "triage_bucket": "direct",
            "triage_priority": "high",
        }

        self.assertFalse(RECONCILE.is_qualified_inbound(payload))


if __name__ == "__main__":
    unittest.main()
