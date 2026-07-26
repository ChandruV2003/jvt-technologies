#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from packet_quality import (
    classify_packet,
    clear_safe_historical_hold,
)


class PacketQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        text_path = root / "packet.txt"
        html_path = root / "packet.html"
        review_path = root / "packet.md"
        body = (
            "Hi BrightPath team,\n\n"
            "We help dental offices turn missed calls and repeated front-desk questions into structured intake notes "
            "that staff can review before returning a patient call. The first step would be a small synthetic workflow "
            "using your call categories, escalation rules, and no-say requirements. Nothing would touch live patient "
            "calls until the office approves the flow, disclosure, and routing behavior.\n\n"
            "Would a short walkthrough be useful?\n"
        )
        text_path.write_text(body, encoding="utf-8")
        html_path.write_text(f"<html><body><p>{body}</p></body></html>", encoding="utf-8")
        review_path.write_text("# Packet\n", encoding="utf-8")
        self.payload = {
            "company_name": "BrightPath Dental",
            "recipient_email": "frontdesk@brightpathdental.com",
            "contact_page": "https://brightpathdental.com/contact",
            "industry": "Dental / Healthcare Admin",
            "likely_pain": "turning missed calls and repeated front-desk questions into structured intake notes",
            "personalized_offer": "a synthetic dental voice intake workflow with staff-controlled escalation rules",
            "subject": "A cleaner missed-call intake flow for BrightPath Dental",
            "review_path": str(review_path),
            "text_path": str(text_path),
            "html_path": str(html_path),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_historical_hold_can_be_cleared_when_current_evidence_passes(self) -> None:
        payload = {**self.payload, "quality_hold_reason": "manual review required after copy regeneration"}
        result = classify_packet(payload, source_queue="review")
        self.assertEqual(result["decision"], "approval_candidate")
        self.assertTrue(result["historical_hold_only"])
        self.assertTrue(result["safe_to_clear_quality_hold"])

        self.assertTrue(clear_safe_historical_hold(payload, result, source="test"))
        self.assertNotIn("quality_hold_reason", payload)
        self.assertEqual(payload["quality_hold_history"][0]["reason"], "manual review required after copy regeneration")

    def test_strict_historical_hold_remains_blocking_until_resolved(self) -> None:
        payload = {**self.payload, "quality_hold_reason": "manual review required after copy regeneration"}
        result = classify_packet(payload, source_queue="approved", strict_historical_hold=True)
        self.assertEqual(result["decision"], "repair_candidate")
        self.assertIn("historical_quality_hold", result["reason_codes"])

    def test_semantic_historical_hold_is_not_auto_cleared(self) -> None:
        payload = {
            **self.payload,
            "quality_hold_reason": "off-target teleservices/call-center provider; false positive",
        }
        result = classify_packet(payload, source_queue="review")
        self.assertEqual(result["decision"], "repair_candidate")
        self.assertFalse(result["safe_to_clear_quality_hold"])
        self.assertIn("historical_quality_hold", result["reason_codes"])

    def test_mismatched_recipient_domain_is_a_hard_hold(self) -> None:
        payload = {**self.payload, "recipient_email": "frontdesk@unrelated-example.org"}
        result = classify_packet(payload, source_queue="review")
        self.assertEqual(result["decision"], "hard_hold")
        self.assertIn("email_domain_mismatch", result["reason_codes"])
        self.assertFalse(result["safe_to_clear_quality_hold"])

    def test_generic_company_identity_is_a_hard_hold(self) -> None:
        payload = {**self.payload, "company_name": "Dentist in Newark, NJ"}
        result = classify_packet(payload, source_queue="review")
        self.assertEqual(result["decision"], "hard_hold")
        self.assertIn("generic_company_name", result["reason_codes"])

    def test_missing_render_is_repairable(self) -> None:
        payload = {**self.payload, "html_path": ""}
        result = classify_packet(payload, source_queue="review")
        self.assertEqual(result["decision"], "repair_candidate")
        self.assertIn("missing_rendered_artifact", result["reason_codes"])

    def test_followup_kind_is_detected(self) -> None:
        payload = {**self.payload, "follow_up_stage": 1}
        result = classify_packet(payload, source_queue="review")
        self.assertEqual(result["kind"], "followup")


if __name__ == "__main__":
    unittest.main()
