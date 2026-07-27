#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import auto_approve_review_followups as followups
import auto_approve_review_initials as initials
from packet_quality import is_auto_approval_candidate


def repair_candidate_quality() -> dict:
    return {
        "decision": "repair_candidate",
        "score": 55,
        "reason_codes": ["unnormalized_company_name"],
        "human_reasons": ["company name looks unnormalized"],
        "historical_hold": False,
        "historical_hold_only": False,
        "safe_to_clear_quality_hold": False,
    }


class AutoApproveReviewInvariantTests(unittest.TestCase):
    def test_model_approval_does_not_bypass_canonical_quality_for_initials(self) -> None:
        self.assert_model_approval_does_not_move_packet(initials, {"company_name": "Lpappas Cpa"})

    def test_model_approval_does_not_bypass_canonical_quality_for_followups(self) -> None:
        self.assert_model_approval_does_not_move_packet(
            followups,
            {"company_name": "Lpappas Cpa", "follow_up_stage": 1, "follow_up_parent_stem": "parent"},
        )

    def test_canonical_quality_pass_requires_approval_candidate_without_reasons(self) -> None:
        self.assertTrue(is_auto_approval_candidate({"decision": "approval_candidate", "human_reasons": []}))
        self.assertFalse(
            is_auto_approval_candidate(
                {"decision": "approval_candidate", "human_reasons": ["needs human review"]}
            )
        )
        self.assertFalse(is_auto_approval_candidate({"decision": "repair_candidate", "human_reasons": []}))

    def assert_model_approval_does_not_move_packet(self, module, payload: dict) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            review = root / "review"
            approved = root / "approved"
            reports = root / "reports"
            review.mkdir(parents=True)
            stem = "packet"
            (review / f"{stem}.json").write_text(json.dumps(payload), encoding="utf-8")

            with (
                mock.patch.object(module, "REVIEW", review),
                mock.patch.object(module, "APPROVED", approved),
                mock.patch.object(module, "REPORT_DIR", reports),
                mock.patch.object(module, "classify_packet", return_value=repair_candidate_quality()),
                mock.patch.object(
                    module,
                    "review_packet",
                    return_value={"approved": True, "reason": "looks okay"},
                ) as review_packet,
                mock.patch.object(sys, "argv", [module.__file__, "--write"]),
                mock.patch("builtins.print"),
            ):
                module.main()

            review_packet.assert_called_once()
            self.assertTrue((review / f"{stem}.json").exists())
            self.assertFalse((approved / f"{stem}.json").exists())


if __name__ == "__main__":
    unittest.main()
