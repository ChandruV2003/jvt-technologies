#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import work_item_materializer as materializer


class WorkItemMaterializerBackoffTests(unittest.TestCase):
    def run_materializer(self, *, failed_age_hours: float) -> tuple[dict, Path, Path]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        task_root = root / "tasks"
        failed_root = task_root / "failed"
        failed_root.mkdir(parents=True)
        policy_path = root / "work-item-materializer-policy.json"
        orchestrator_path = root / "latest-orchestrator.json"

        policy_path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "materializer": {
                        "default_cadence": "daily",
                        "max_items_per_run": 20,
                    },
                    "rules": [
                        {
                            "name": "voice bridge readiness next step",
                            "lane": "voice-intake",
                            "title_contains": ["local audio bridge"],
                            "action": "task",
                            "task_type": "local_audio_bridge_next_step",
                            "cadence": "hourly",
                            "failure_backoff_hours": 6,
                        }
                    ],
                    "epic_rules": [],
                }
            ),
            encoding="utf-8",
        )
        orchestrator_path.write_text(
            json.dumps(
                {
                    "generated_at": "2026-07-27T12:00:00+00:00",
                    "work_items": [
                        {
                            "id": "voice-bridge-readiness",
                            "lane": "voice-intake",
                            "title": "Advance local audio bridge readiness",
                            "recommended_action": "Run the local readiness check.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        failed_path = failed_root / "previous-failed-task.json"
        failed_path.write_text(
            json.dumps(
                {
                    "id": "previous-failed-task",
                    "type": "local_audio_bridge_next_step",
                    "source_rule": "voice bridge readiness next step",
                    "runner_updated_at": (
                        datetime.now(timezone.utc) - timedelta(hours=failed_age_hours)
                    ).isoformat(timespec="seconds"),
                    "runner_result": {"ok": False},
                }
            ),
            encoding="utf-8",
        )

        with (
            mock.patch.object(materializer, "POLICY_PATH", policy_path),
            mock.patch.object(materializer, "ORCHESTRATOR_PATH", orchestrator_path),
            mock.patch.object(materializer, "TASK_ROOT", task_root),
            mock.patch.object(materializer, "EPIC_ROOT", root / "epics"),
            mock.patch.object(materializer, "STATE_ROOT", root / "state"),
        ):
            report = materializer.materialize(dry_run=False)

        return report, failed_path, task_root / "pending"

    def test_recent_matching_failure_skips_materialization_during_backoff(self) -> None:
        report, failed_path, pending_root = self.run_materializer(failed_age_hours=1)

        self.assertEqual(report["created_count"], 0)
        self.assertEqual(report["skipped_count"], 1)
        self.assertEqual(report["skipped"][0]["reason"], "failure_backoff_active")
        self.assertEqual(report["skipped"][0]["failed_task_id"], "previous-failed-task")
        self.assertEqual(report["skipped"][0]["failure_backoff_hours"], 6.0)
        self.assertTrue(failed_path.exists())
        self.assertEqual(list(pending_root.glob("*.json")), [])

    def test_matching_failure_allows_materialization_after_backoff_expires(self) -> None:
        report, failed_path, pending_root = self.run_materializer(failed_age_hours=7)

        self.assertEqual(report["created_count"], 1)
        self.assertEqual(report["skipped_count"], 0)
        self.assertEqual(report["created"][0]["type"], "local_audio_bridge_next_step")
        self.assertTrue(Path(report["created"][0]["path"]).exists())
        self.assertTrue(failed_path.exists())
        self.assertEqual(len(list(pending_root.glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
