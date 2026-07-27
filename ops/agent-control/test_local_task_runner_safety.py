#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


RUNNER_PATH = Path(__file__).with_name("local_task_runner.py")
SPEC = importlib.util.spec_from_file_location("local_task_runner", RUNNER_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class LocalTaskRunnerSafetyTests(unittest.TestCase):
    def assignment(self) -> dict:
        return {
            "codex_cli_allowed": False,
            "self_review": "standard",
        }

    def test_read_only_safety_language_does_not_fail_review(self) -> None:
        result = {
            "ok": True,
            "steps": [
                {
                    "name": "status",
                    "ok": True,
                    "stdout_tail": [
                        "No mining, staking, wallet creation, or publishing is allowed."
                    ],
                }
            ],
            "artifacts": [],
            "guardrail": "Status only. No external action.",
        }

        review = RUNNER.self_review_task_result(
            {"type": "codex_escalation_status"},
            result,
            self.assignment(),
        )

        self.assertTrue(review["ok"])
        self.assertEqual(review["blocking_finding_count"], 0)

    def test_explicit_external_action_result_fails_review(self) -> None:
        result = {
            "ok": True,
            "external_action_performed": True,
            "artifacts": [],
            "guardrail": "Internal task only.",
        }

        review = RUNNER.self_review_task_result(
            {"type": "status"},
            result,
            self.assignment(),
        )

        self.assertFalse(review["ok"])
        self.assertEqual(
            review["findings"][0]["code"],
            "result_declares_external_action",
        )

    def test_retry_ignores_prior_runner_result_language(self) -> None:
        task = {
            "type": "codex_escalation_status",
            "goal": "Refresh internal Codex status.",
            "runner_result": {
                "steps": [
                    {
                        "stdout_tail": [
                            "No mining, staking, wallet creation, or publishing."
                        ]
                    }
                ]
            },
            "runner_updated_at": "2026-07-27T00:00:00+00:00",
        }

        self.assertIsNone(RUNNER.hold_reason(task))

    def test_requested_disallowed_action_still_holds(self) -> None:
        task = {
            "type": "research",
            "goal": "Start mining cryptocurrency.",
        }

        self.assertEqual(
            RUNNER.hold_reason(task),
            "Task text contains approval-gated/disallowed phrase: mining",
        )

    def test_approved_quality_reconcile_handler_runs_demotion_gate_only(self) -> None:
        self.assertIn("approved_quality_reconcile", RUNNER.HANDLERS)

        with mock.patch.object(RUNNER, "run_command", return_value={"ok": True}) as run_command:
            result = RUNNER.approved_quality_reconcile({})

        run_command.assert_called_once_with(
            "approved_quality_reconcile",
            ["python3", "outreach/tools/quality_gate_approved.py", "--move-held"],
            timeout=90,
        )
        self.assertTrue(result["ok"])
        self.assertIn("No packets are approved or sent.", result["guardrail"])


if __name__ == "__main__":
    unittest.main()
