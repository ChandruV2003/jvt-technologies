#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import audioop
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect


app = FastAPI(title="JVT Local Audio Bridge", version="0.1.0")
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = APP_ROOT / "data" / "local-audio-bridge"
LATEST_REGRESSION = DATA_ROOT / "latest-regression.json"
MULAW_SILENCE = base64.b64encode(b"\xff" * 160).decode("ascii")


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def bridge_ready() -> bool:
    return truthy(os.environ.get("JVT_LOCAL_AUDIO_BRIDGE_READY", "0"))


def int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def load_latest_regression() -> dict[str, Any]:
    if not LATEST_REGRESSION.exists():
        return {"ok": False, "status": "missing"}
    try:
        return json.loads(LATEST_REGRESSION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "unreadable", "error": str(exc)}


class BridgeSession:
    def __init__(self) -> None:
        self.stream_sid = ""
        self.call_sid = ""
        self.media_events = 0
        self.speech_frames = 0
        self.quiet_frames = 0
        self.max_rms = 0
        self.turn_detected = False
        self.threshold = int_env("JVT_LOCAL_AUDIO_BRIDGE_RMS_THRESHOLD", 350)
        self.min_speech_frames = int_env("JVT_LOCAL_AUDIO_BRIDGE_MIN_SPEECH_FRAMES", 8)
        self.end_quiet_frames = int_env("JVT_LOCAL_AUDIO_BRIDGE_END_QUIET_FRAMES", 5)

    def ingest_media(self, payload: str) -> dict[str, Any] | None:
        self.media_events += 1
        try:
            mulaw = base64.b64decode(payload)
            pcm16 = audioop.ulaw2lin(mulaw, 2)
            rms = audioop.rms(pcm16, 2)
        except Exception as exc:
            return {"type": "bridge.error", "error": f"media_decode_failed: {exc}"}

        self.max_rms = max(self.max_rms, rms)
        if rms >= self.threshold:
            self.speech_frames += 1
            self.quiet_frames = 0
        elif self.speech_frames:
            self.quiet_frames += 1

        if (
            not self.turn_detected
            and self.speech_frames >= self.min_speech_frames
            and self.quiet_frames >= self.end_quiet_frames
        ):
            self.turn_detected = True
            return {
                "type": "bridge.turn.detected",
                "streamSid": self.stream_sid,
                "callSid": self.call_sid,
                "media_events": self.media_events,
                "speech_frames": self.speech_frames,
                "quiet_frames": self.quiet_frames,
                "max_rms": self.max_rms,
                "transcript": "Synthetic local turn detected. STT/model/TTS are still draft stages.",
                "response_text": "Thanks. I can help collect the details and route this for review.",
            }
        return None


@app.get("/health")
def health() -> dict[str, Any]:
    regression = load_latest_regression()
    return {
        "ok": bridge_ready(),
        "ready": bridge_ready(),
        "status": "ready" if bridge_ready() else "pipeline-draft",
        "generated_at": utc_now(),
        "contract": {
            "input": "Twilio Media Streams JSON frames.",
            "output": "Twilio-compatible media frames or bridge transcript/error events.",
            "audio_format": "8kHz PCMU media payloads for Twilio output.",
        },
        "pipeline": {
            "vad": "energy-rms",
            "stt": "placeholder",
            "model": "not-invoked",
            "tts": "placeholder-silence",
            "latest_regression_ok": bool(regression.get("ok")),
            "latest_regression_generated_at": regression.get("generated_at"),
        },
        "safety_boundary": "Pipeline draft only unless JVT_LOCAL_AUDIO_BRIDGE_READY=1. Do not route live calls here until STT/TTS latency and disclosure are validated.",
    }


@app.websocket("/twilio-media")
async def twilio_media(websocket: WebSocket) -> None:
    await websocket.accept()
    session = BridgeSession()
    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            event_name = str(event.get("event") or "")
            if event_name == "start":
                start = event.get("start") or {}
                session.stream_sid = str(start.get("streamSid") or event.get("streamSid") or "")
                session.call_sid = str(start.get("callSid") or "")
                await websocket.send_json({
                    "type": "bridge.status",
                    "status": "accepted",
                    "streamSid": session.stream_sid,
                    "callSid": session.call_sid,
                    "ready": bridge_ready(),
                    "pipeline": "energy-vad-draft",
                    "transcript": "Local audio bridge accepted the stream; realtime STT/TTS is not enabled in pipeline-draft mode.",
                })
            elif event_name == "media":
                media = event.get("media") or {}
                payload = str(media.get("payload") or "")
                response = session.ingest_media(payload)
                if response:
                    await websocket.send_json(response)
                    await websocket.send_json({
                        "event": "media",
                        "streamSid": session.stream_sid,
                        "media": {"payload": MULAW_SILENCE},
                    })
                    await websocket.send_json({
                        "event": "mark",
                        "streamSid": session.stream_sid,
                        "mark": {"name": "jvt-local-bridge-draft-response"},
                    })
            elif event_name == "stop":
                await websocket.send_json({
                    "type": "bridge.status",
                    "status": "stopped",
                    "streamSid": session.stream_sid,
                    "callSid": session.call_sid,
                    "media_events": session.media_events,
                    "speech_frames": session.speech_frames,
                    "turn_detected": session.turn_detected,
                    "max_rms": session.max_rms,
                    "transcript": f"Local bridge stopped after {session.media_events} media frame(s).",
                })
                break
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "bridge.error", "error": str(exc)})
