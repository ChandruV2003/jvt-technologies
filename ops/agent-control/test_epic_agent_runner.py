#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import epic_agent_runner as runner


class EpicAgentRunnerTests(unittest.TestCase):
    def test_usage_events_deduplicates_log_and_done_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            done = root / "done"
            done.mkdir(parents=True)
            usage_log = root / "usage.jsonl"
            finished_at = "2026-07-27T15:56:44+00:00"
            usage_log.write_text(
                json.dumps(
                    {
                        "epic_id": "epic-1",
                        "mode": "codex_workspace_write",
                        "finished_at": finished_at,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (done / "epic-1.json").write_text(
                json.dumps(
                    {
                        "id": "epic-1",
                        "execution_mode": "codex_workspace_write",
                        "epic_agent_updated_at": finished_at,
                        "epic_agent_result": {"mode": "codex_workspace_write"},
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(runner, "EPIC_ROOT", root),
                mock.patch.object(runner, "USAGE_LOG_PATH", usage_log),
            ):
                events = runner.usage_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["epic_id"], "epic-1")

    def test_recovers_codex_path_hold_when_cli_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            held = root / "held"
            held.mkdir(parents=True)
            cli = root / "codex"
            cli.write_text("#!/bin/sh\n", encoding="utf-8")
            cli.chmod(0o755)
            epic = held / "epic-1.json"
            epic.write_text(
                json.dumps(
                    {
                        "id": "epic-1",
                        "status": "queued",
                        "epic_agent_result": {
                            "reason": "Codex CLI missing at /old/location/codex.",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(runner, "EPIC_ROOT", root),
                mock.patch.object(runner, "CODEX_CLI", cli),
            ):
                recovered = runner.recover_retryable_held()

            queued = root / "queued" / "epic-1.json"
            payload = json.loads(queued.read_text(encoding="utf-8"))
            held_exists = epic.exists()

        self.assertEqual(len(recovered), 1)
        self.assertFalse(held_exists)
        self.assertNotIn("epic_agent_result", payload)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["epic_retry_history"][0]["resolved_codex_cli"], str(cli))

    def test_does_not_retry_a_policy_hold(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            held = root / "held"
            held.mkdir(parents=True)
            cli = root / "codex"
            cli.write_text("#!/bin/sh\n", encoding="utf-8")
            os.chmod(cli, 0o755)
            epic = held / "epic-2.json"
            epic.write_text(
                json.dumps(
                    {
                        "id": "epic-2",
                        "epic_agent_result": {
                            "reason": "Epic contains approval-gated direct-action phrase: send prospect email",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(runner, "EPIC_ROOT", root),
                mock.patch.object(runner, "CODEX_CLI", cli),
            ):
                recovered = runner.recover_retryable_held()
            held_exists = epic.exists()

        self.assertEqual(recovered, [])
        self.assertTrue(held_exists)


if __name__ == "__main__":
    unittest.main()
