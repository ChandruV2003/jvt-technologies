#!/usr/bin/env python3
from __future__ import annotations

import unittest

from codex_recommendation_materializer import build_epic, referenced_paths


class CodexRecommendationMaterializerTests(unittest.TestCase):
    def test_extracts_and_deduplicates_repository_python_paths(self) -> None:
        text = (
            "Add `outreach/tools/packet_quality.py`, then refactor "
            "[the gate](outreach/tools/quality_gate_approved.py:20). "
            "Use outreach/tools/packet_quality.py again."
        )
        self.assertEqual(
            referenced_paths(text),
            [
                "outreach/tools/packet_quality.py",
                "outreach/tools/quality_gate_approved.py",
            ],
        )

    def test_epic_is_workspace_write_and_has_complete_roi_case(self) -> None:
        epic = build_epic(
            epic_id="codex-recommendation-123456789abc",
            metadata={"task_id": "task-1", "generated_at": "2026-07-26T00:00:00+00:00"},
            recommendation="Implement a shared classifier.",
            scope_paths=["outreach/tools/packet_quality.py"],
            missing_paths=["outreach/tools/packet_quality.py"],
        )
        self.assertEqual(epic["execution_mode"], "codex_workspace_write")
        self.assertFalse(epic["requires_approval"])
        self.assertEqual(
            set(epic["roi_case"]),
            {
                "revenue_goal_link",
                "expected_business_value",
                "why_codex_is_worth_it",
                "success_metric",
                "fallback_if_not_run",
            },
        )


if __name__ == "__main__":
    unittest.main()
