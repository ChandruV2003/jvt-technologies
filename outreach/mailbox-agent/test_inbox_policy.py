#!/usr/bin/env python3
from __future__ import annotations

import unittest

from inbox_policy import is_internal_sender, is_system_sender, qualified_external_inbound


class InboxPolicyTests(unittest.TestCase):
    def test_known_operator_sender_is_internal(self) -> None:
        self.assertTrue(is_internal_sender("jvtvasu@icloud.com"))

    def test_bank_alert_is_system(self) -> None:
        self.assertTrue(is_system_sender("alerts@bankofamerica.com"))

    def test_internal_direct_message_is_not_qualified(self) -> None:
        payload = {
            "from": "Vasudevan Chandrabose <jvtvasu@icloud.com>",
            "triage_bucket": "direct",
            "triage_priority": "high",
            "triage_action": "review",
        }

        self.assertFalse(qualified_external_inbound(payload))

    def test_external_direct_message_is_qualified(self) -> None:
        payload = {
            "from": "Owner <owner@example-business.com>",
            "triage_bucket": "direct",
            "triage_priority": "high",
            "triage_action": "review",
        }

        self.assertTrue(qualified_external_inbound(payload))


if __name__ == "__main__":
    unittest.main()
