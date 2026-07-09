#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect


app = FastAPI(title="JVT Local Audio Bridge", version="0.1.0")


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def bridge_ready() -> bool:
    return truthy(os.environ.get("JVT_LOCAL_AUDIO_BRIDGE_READY", "0"))


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": bridge_ready(),
        "ready": bridge_ready(),
        "status": "ready" if bridge_ready() else "contract-only",
        "generated_at": utc_now(),
        "contract": {
            "input": "Twilio Media Streams JSON frames.",
            "output": "Twilio-compatible media frames or bridge transcript/error events.",
            "audio_format": "8kHz PCMU media payloads for Twilio output.",
        },
        "safety_boundary": "Contract stub only unless JVT_LOCAL_AUDIO_BRIDGE_READY=1. Do not route live calls here until STT/TTS latency and disclosure are validated.",
    }


@app.websocket("/twilio-media")
async def twilio_media(websocket: WebSocket) -> None:
    await websocket.accept()
    stream_sid = ""
    call_sid = ""
    media_events = 0
    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            event_name = str(event.get("event") or "")
            if event_name == "start":
                start = event.get("start") or {}
                stream_sid = str(start.get("streamSid") or "")
                call_sid = str(start.get("callSid") or "")
                await websocket.send_json({
                    "type": "bridge.status",
                    "status": "accepted",
                    "streamSid": stream_sid,
                    "callSid": call_sid,
                    "ready": bridge_ready(),
                    "transcript": "Local audio bridge accepted the stream; realtime STT/TTS is not enabled in contract-only mode.",
                })
            elif event_name == "media":
                media_events += 1
            elif event_name == "stop":
                await websocket.send_json({
                    "type": "bridge.status",
                    "status": "stopped",
                    "streamSid": stream_sid,
                    "callSid": call_sid,
                    "media_events": media_events,
                    "transcript": f"Local bridge stopped after {media_events} media frame(s).",
                })
                break
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "bridge.error", "error": str(exc)})
