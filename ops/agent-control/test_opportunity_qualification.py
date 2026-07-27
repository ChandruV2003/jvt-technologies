#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from opportunity_qualification import qualify_items


class OpportunityQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_inbox(self, bucket: str, name: str, payload: dict) -> Path:
        path = self.repo_root / "outreach" / "inbox" / bucket / "2026-07-01" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_relocated_source_is_qualified_and_deduplicated(self) -> None:
        source = self.write_inbox(
            "reviewed",
            "message-uid-101.json",
            {
                "uid": 101,
                "from": "Owner <owner@example.com>",
                "sender_email": "owner@example.com",
                "subject": "Re: Pilot",
            },
        )
        stale = self.repo_root / "outreach" / "inbox" / "new" / "2026-07-01" / source.name
        items = [
            {
                "id": 1,
                "kind": "opportunity",
                "account_name": "Example Co",
                "contact_email": "owner@example.com",
                "stage": "reply-sent-awaiting-next",
                "source": str(stale),
            },
            {
                "id": 2,
                "kind": "opportunity",
                "account_name": "Example Co",
                "contact_email": "owner@example.com",
                "stage": "reply-sent-awaiting-next",
                "source": str(source),
            },
        ]

        result = qualify_items(items, self.repo_root)

        self.assertTrue(result[0]["qualified"])
        self.assertFalse(result[0]["duplicate"])
        self.assertFalse(result[1]["qualified"])
        self.assertTrue(result[1]["duplicate"])
        self.assertEqual(result[1]["duplicate_of"], 1)

    def test_internal_and_promotional_messages_are_excluded(self) -> None:
        internal = self.write_inbox(
            "reviewed",
            "internal-uid-102.json",
            {
                "uid": 102,
                "agent_triage_status": "reviewed_internal",
                "agent_triage_reason": "operator_or_internal_sender",
            },
        )
        promotional = self.write_inbox(
            "closed",
            "promo-uid-103.json",
            {
                "uid": 103,
                "agent_triage_status": "closed_promotional_or_newsletter",
                "agent_triage_reason": "promotional_or_newsletter_marker",
            },
        )
        result = qualify_items(
            [
                {
                    "id": 1,
                    "kind": "opportunity",
                    "account_name": "Internal",
                    "contact_email": "internal@example.com",
                    "stage": "inbound-hit-needs-review",
                    "source": str(internal),
                },
                {
                    "id": 2,
                    "kind": "opportunity",
                    "account_name": "Newsletter",
                    "contact_email": "news@example.com",
                    "stage": "inbound-hit-needs-review",
                    "source": str(promotional),
                },
            ],
            self.repo_root,
        )

        self.assertEqual(result[0]["qualification_status"], "internal")
        self.assertFalse(result[0]["warm"])
        self.assertEqual(result[1]["qualification_status"], "disqualified")
        self.assertFalse(result[1]["active"])

    def test_unattached_pilot_decision_remains_a_concept(self) -> None:
        result = qualify_items(
            [
                {
                    "id": "dental-concept",
                    "kind": "pilot_decision",
                    "account_name": "Dental office",
                    "contact_email": "",
                    "stage": "pilot-discovery-needed",
                    "source": "",
                }
            ],
            self.repo_root,
        )

        self.assertEqual(result[0]["qualification_status"], "concept")
        self.assertEqual(result[0]["conversion_stage"], "concept")
        self.assertFalse(result[0]["qualified"])


if __name__ == "__main__":
    unittest.main()
