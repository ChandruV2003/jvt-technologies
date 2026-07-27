#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import audioop
import base64
import os
import unittest
from unittest.mock import patch

import local_audio_bridge_stub as bridge


def payload(pcm16: bytes) -> str:
    return base64.b64encode(audioop.lin2ulaw(pcm16, 2)).decode("ascii")


class LocalAudioBridgeUnitTests(unittest.TestCase):
    def test_session_detects_and_resets_multiple_turns(self) -> None:
        speech = payload((1500).to_bytes(2, "little", signed=True) * 160)
        silence = base64.b64encode(b"\xff" * 160).decode("ascii")
        with patch.dict(
            os.environ,
            {
                "JVT_LOCAL_AUDIO_BRIDGE_MIN_SPEECH_FRAMES": "2",
                "JVT_LOCAL_AUDIO_BRIDGE_END_QUIET_FRAMES": "2",
            },
        ):
            session = bridge.BridgeSession()
        completed = []
        for _ in range(2):
            self.assertIsNone(session.ingest_media(speech))
            self.assertIsNone(session.ingest_media(speech))
            self.assertIsNone(session.ingest_media(silence))
            completed.append(session.ingest_media(silence))

        self.assertEqual([item["turn"] for item in completed], [1, 2])
        self.assertTrue(all(item["pcm16"] for item in completed))
        self.assertEqual(session.turn_count, 2)

    def test_invalid_media_is_reported(self) -> None:
        event = bridge.BridgeSession().ingest_media("not-base64")
        self.assertEqual(event["type"], "bridge.error")
        self.assertIn("media_decode_failed", event["error"])

    def test_router_failure_uses_safe_fallback(self) -> None:
        with patch.dict(
            os.environ,
            {
                "JVT_MODEL_ROUTER_URL": "http://127.0.0.1:9",
                "JVT_LOCAL_AUDIO_BRIDGE_ROUTER_TIMEOUT": "0.2",
            },
        ):
            text, ok = asyncio.run(bridge.route_response("Please help."))
        self.assertFalse(ok)
        self.assertEqual(text, bridge.FALLBACK_RESPONSE)

    def test_tts_returns_non_silent_pcmu_frames(self) -> None:
        frames = bridge.synthesize_pcmu_frames("Thanks. A person will review your request.")
        rms_values = [
            audioop.rms(audioop.ulaw2lin(base64.b64decode(frame), 2), 2)
            for frame in frames
        ]
        self.assertGreater(max(rms_values), 100)
        self.assertTrue(all(len(base64.b64decode(frame)) == 160 for frame in frames))

    def test_model_tokens_are_removed(self) -> None:
        self.assertEqual(
            bridge.clean_model_response("Sure, I can help.<|im_end|>"),
            "Sure, I can help.",
        )


if __name__ == "__main__":
    unittest.main()
