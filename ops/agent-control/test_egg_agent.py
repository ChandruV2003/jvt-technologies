#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


EGG_PATH = Path(__file__).with_name("egg_agent.py")
SPEC = importlib.util.spec_from_file_location("egg_agent", EGG_PATH)
assert SPEC and SPEC.loader
EGG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EGG)


def baseline_snapshot() -> dict:
    return {
        "queues": {"draft": 0, "review": 0, "approved": 8, "sent": 0, "replied": 0},
        "inbox": {"new": 0, "reviewed": 0, "closed": 0},
        "tasks": {"pending": 1, "running": 0, "completed": 0, "failed": 0, "held": 0},
        "task_health": {"recent_failed_type_count": 0, "recent_failed_types": []},
        "orchestrator": {"work_item_count": 0, "age_seconds": 0, "quotas": {}},
        "watchdog": {"overall_ok": True, "finding_count": 0},
        "model_router": {"ok": True},
        "codex_escalation": {"ok": True, "age_seconds": 0, "usage": {"remaining": {"total_execute": 0}}},
        "codex_recommendation": {},
        "ops_db": {"ok": True, "age_seconds": 0},
        "opportunity_manager": {"warm_count": 0, "response_needed_count": 0},
        "lead_research": {"generated_at": "2026-07-27T00:00:00+00:00", "new_leads_added": 2, "drafts_created": 2},
        "voice": {"demo_ready": False, "local_bridge_ready": False, "sample_state": {"samples": 0, "renders": 0}},
        "custom_pilot_pipeline": {"age_seconds": 0},
        "conversion_pipeline": {"age_seconds": 0, "stale_next_action_count": 0},
        "public_conversion_kv_sync": {"age_seconds": 0, "ok": True, "unreconciled_count": 0},
        "reply_reconciliation": {"age_seconds": 0, "matched_count": 0},
        "warm_followup_samples": {"age_seconds": 0},
        "materializer": {"unmatched_count": 0},
        "artifact_ages": {"content_backlog": 0, "meeting_packet_today": 0, "insurance_proof_today": 0},
        "lead_quality": {"age_seconds": 10, "sections": {"approved": {"total": 8, "pass": 7, "hold": 1}}},
        "quality_hold_repair": {},
        "fresh_lead_packets": {"source_research_generated_at": "2026-07-27T00:00:00+00:00"},
        "followup_review_count": 0,
    }


class EggAgentQualityReconcileTests(unittest.TestCase):
    def test_approved_quality_reconcile_is_safe_and_preempts_stale_audit_candidate(self) -> None:
        self.assertIn("approved_quality_reconcile", EGG.SAFE_TASK_TYPES)

        candidates = EGG.deterministic_candidates(baseline_snapshot())
        reconcile = [item for item in candidates if item["type"] == "approved_quality_reconcile"]
        stale_audit = [
            item
            for item in candidates
            if item["type"] == "lead_quality_audit" and item.get("reason") == "lead quality audit stale"
        ]

        self.assertEqual(len(reconcile), 1)
        self.assertEqual(reconcile[0]["dedupe_key"], "approved-quality-reconcile")
        self.assertEqual(reconcile[0]["priority_rank"], 1)
        self.assertEqual(stale_audit, [])

    def test_approved_quality_reconcile_uses_strict_self_review(self) -> None:
        task = EGG.build_task(
            {
                "type": "approved_quality_reconcile",
                "goal": "Demote held approved packets.",
                "feature": "outreach-quality",
                "reason": "approved hold",
            },
            "approved-quality-reconcile-test",
        )

        self.assertEqual(task["self_review"], "strict")

    def test_lifetime_failure_archive_does_not_trigger_codex(self) -> None:
        snapshot = baseline_snapshot()
        snapshot["tasks"]["failed"] = 54
        snapshot["codex_escalation"]["usage"]["remaining"]["total_execute"] = 8

        candidates = EGG.deterministic_candidates(snapshot)

        self.assertNotIn("codex_escalation_request", {item["type"] for item in candidates})

    def test_latest_success_resolves_prior_failure_for_task_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            task_root = Path(temp)
            failed = task_root / "failed"
            completed = task_root / "completed"
            held = task_root / "held"
            for path in (failed, completed, held):
                path.mkdir(parents=True)
            failed_path = failed / "old-failure.json"
            failed_path.write_text(json.dumps({"type": "voice_readiness_check"}), encoding="utf-8")
            completed_path = completed / "new-success.json"
            completed_path.write_text(json.dumps({"type": "voice_readiness_check"}), encoding="utf-8")
            unresolved_path = failed / "current-failure.json"
            unresolved_path.write_text(json.dumps({"type": "vertical_lead_research_refresh"}), encoding="utf-8")
            now = time.time()
            os.utime(failed_path, (now - 120, now - 120))
            os.utime(completed_path, (now - 60, now - 60))
            os.utime(unresolved_path, (now - 30, now - 30))

            with mock.patch.object(EGG, "TASK_ROOT", task_root):
                health = EGG.terminal_task_health()

        self.assertEqual(health["recent_failed_type_count"], 1)
        self.assertEqual(health["recent_failed_types"], ["vertical_lead_research_refresh"])

    def test_missing_reply_state_schedules_reconciliation(self) -> None:
        snapshot = baseline_snapshot()
        snapshot["opportunity_manager"]["qualified_count"] = 1
        snapshot["reply_reconciliation"]["age_seconds"] = None

        candidates = EGG.deterministic_candidates(snapshot)

        self.assertIn("reply_reconciliation", {item["type"] for item in candidates})

    def test_overdue_conversion_action_schedules_refresh(self) -> None:
        snapshot = baseline_snapshot()
        snapshot["conversion_pipeline"]["stale_next_action_count"] = 1

        candidates = EGG.deterministic_candidates(snapshot)
        refresh = [item for item in candidates if item["type"] == "conversion_pipeline_refresh"]

        self.assertEqual(len(refresh), 1)
        self.assertEqual(refresh[0]["priority_rank"], 1)

    def test_stale_public_conversion_sync_schedules_reconciliation(self) -> None:
        snapshot = baseline_snapshot()
        snapshot["public_conversion_kv_sync"] = {
            "age_seconds": None,
            "ok": False,
            "failed_count": 1,
            "unreconciled_count": 1,
        }

        candidates = EGG.deterministic_candidates(snapshot)
        sync = [item for item in candidates if item["type"] == "public_conversion_kv_sync"]

        self.assertEqual(len(sync), 1)
        task = EGG.build_task(sync[0], "public-conversion-kv-sync-test")
        self.assertEqual(task["level"], "story")
        self.assertEqual(task["self_review"], "strict")


if __name__ == "__main__":
    unittest.main()
