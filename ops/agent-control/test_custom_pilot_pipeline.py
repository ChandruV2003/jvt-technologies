#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import custom_pilot_pipeline as pipeline


class CustomPilotPipelineTests(unittest.TestCase):
    def test_conversion_assets_are_complete_and_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            item = {
                "account_name": "Example Law",
                "contact_email": "owner@example.com",
                "service_slug": "private-doc-intel",
                "source_subject": "Re: Workflow idea",
                "stage": "reply-sent-awaiting-next",
                "conversion_stage": "qualified-awaiting-next",
            }
            patches = [
                patch.object(pipeline, "PROPOSAL_ROOT", root / "proposals"),
                patch.object(pipeline, "SOW_ROOT", root / "sow"),
                patch.object(pipeline, "REPLY_ROOT", root / "replies"),
                patch.object(pipeline, "PROSPECT_ROOT", root / "prospects"),
                patch.object(pipeline, "SYNTHETIC_ROOT", root / "synthetic"),
            ]
            for context in patches:
                context.start()
            self.addCleanup(lambda: [context.stop() for context in reversed(patches)])

            first = pipeline.build_conversion_assets(item)
            proposal = Path(first["paths"]["proposal"])
            proposal.write_text("operator edit\n", encoding="utf-8")
            second = pipeline.build_conversion_assets(item)

            self.assertTrue(first["ready"])
            self.assertEqual(len(first["created"]), 6)
            self.assertTrue(second["ready"])
            self.assertEqual(second["created"], [])
            self.assertEqual(proposal.read_text(encoding="utf-8"), "operator edit\n")

    def test_demo_scenario_matches_service(self) -> None:
        self.assertIn("dental office", "\n".join(pipeline.synthetic_demo_lines("ai-voice-intake")))
        self.assertIn("board meeting", "\n".join(pipeline.synthetic_demo_lines("workflow-automation")))
        self.assertIn("estate-planning", "\n".join(pipeline.synthetic_demo_lines("private-doc-intel")))


if __name__ == "__main__":
    unittest.main()
