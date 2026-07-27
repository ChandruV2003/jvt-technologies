#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import codex_recommendation_materializer as materializer
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

    def test_existing_scope_paths_remain_implementation_deliverables(self) -> None:
        epic = build_epic(
            epic_id="codex-recommendation-123456789abc",
            metadata={"task_id": "task-1", "generated_at": "2026-07-26T00:00:00+00:00"},
            recommendation="Fix behavior in an existing file.",
            scope_paths=["outreach/tools/packet_quality.py"],
            missing_paths=[],
        )
        self.assertEqual(epic["deliverables"], ["outreach/tools/packet_quality.py"])

    def test_existing_files_do_not_suppress_a_new_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scope_path = root / "outreach" / "tools" / "packet_quality.py"
            scope_path.parent.mkdir(parents=True)
            scope_path.write_text("# existing implementation target\n", encoding="utf-8")
            result_path = root / "latest-result.json"
            result_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-27T00:00:00+00:00",
                        "task_id": "task-2",
                        "ok": True,
                        "model": "gpt-5.5",
                        "final_message": "Fix behavior in outreach/tools/packet_quality.py.",
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(materializer, "REPO_ROOT", root),
                mock.patch.object(materializer, "RESULT_PATH", result_path),
                mock.patch.object(materializer, "ESCALATION_PATH", root / "missing-escalation.json"),
                mock.patch.object(materializer, "EPIC_ROOT", root / "epics"),
            ):
                report = materializer.materialize(dry_run=True)

        self.assertEqual(report["status"], "would_queue")
        self.assertTrue(report["implementation_required"])
        self.assertEqual(report["existing_paths"], ["outreach/tools/packet_quality.py"])
        self.assertEqual(report["missing_paths"], [])
        self.assertTrue(report["epic_id"].startswith("codex-recommendation-"))


if __name__ == "__main__":
    unittest.main()
