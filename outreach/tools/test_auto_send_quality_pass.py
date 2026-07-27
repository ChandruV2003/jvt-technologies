#!/usr/bin/env python3
from __future__ import annotations

import unittest

from auto_send_quality_pass import effective_critical_findings


class AutoSendQualityPassTests(unittest.TestCase):
    def test_successful_reconcile_clears_only_outreach_quality_fault(self) -> None:
        findings = [
            {"severity": "critical", "area": "outreach-qc", "message": "one packet failed"},
            {"severity": "critical", "area": "mailbox", "message": "listener stale"},
        ]

        self.assertEqual(
            effective_critical_findings(findings, {"returncode": 0}),
            [{"severity": "critical", "area": "mailbox", "message": "listener stale"}],
        )

    def test_failed_reconcile_preserves_all_faults(self) -> None:
        findings = [{"severity": "critical", "area": "outreach-qc", "message": "one packet failed"}]

        self.assertEqual(
            effective_critical_findings(findings, {"returncode": 1}),
            findings,
        )


if __name__ == "__main__":
    unittest.main()
