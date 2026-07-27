#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
