#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import audioop
import base64
import json
import math
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets


APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = APP_ROOT / "data" / "local-audio-bridge"
LATEST_REGRESSION = DATA_ROOT / "latest-regression.json"
FRAME_SAMPLES = 160
SAMPLE_RATE = 8000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def pcm16_sine_frame(frame_index: int, *, frequency: float = 440.0, amplitude: int = 9000) -> bytes:
    values = []
    phase_offset = frame_index * FRAME_SAMPLES
    for sample_index in range(FRAME_SAMPLES):
        sample = int(amplitude * math.sin(2 * math.pi * frequency * (phase_offset + sample_index) / SAMPLE_RATE))
        values.append(struct.pack("<h", sample))
    return b"".join(values)


def mulaw_payload(pcm16: bytes) -> str:
    return base64.b64encode(audioop.lin2ulaw(pcm16, 2)).decode("ascii")


def silence_payload() -> str:
    return base64.b64encode(b"\xff" * FRAME_SAMPLES).decode("ascii")


async def run_regression(url: str, voice_frames: int, silence_frames: int, timeout_seconds: float) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    stream_sid = "MT_SYNTHETIC_JVT_LOCAL_BRIDGE"
    async with websockets.connect(url, open_timeout=timeout_seconds) as websocket:
        await websocket.send(json.dumps({
            "event": "start",
            "streamSid": stream_sid,
            "start": {
                "streamSid": stream_sid,
                "callSid": "CA_SYNTHETIC_JVT_LOCAL_BRIDGE",
            },
        }))
        messages.append(json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)))

        for frame_index in range(voice_frames):
            await websocket.send(json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": mulaw_payload(pcm16_sine_frame(frame_index))},
            }))
            await asyncio.sleep(0)

        for _ in range(silence_frames):
            await websocket.send(json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": silence_payload()},
            }))
            await asyncio.sleep(0)
            while True:
                try:
                    messages.append(json.loads(await asyncio.wait_for(websocket.recv(), timeout=0.05)))
                except asyncio.TimeoutError:
                    break

        await websocket.send(json.dumps({"event": "stop", "streamSid": stream_sid}))
        while True:
            try:
                messages.append(json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)))
            except asyncio.TimeoutError:
                break
            if messages[-1].get("status") == "stopped":
                break

    turn_detected = any(message.get("type") == "bridge.turn.detected" for message in messages)
    returned_media = any(message.get("event") == "media" and (message.get("media") or {}).get("payload") for message in messages)
    stopped = any(message.get("status") == "stopped" for message in messages)
    accepted = any(message.get("status") == "accepted" for message in messages)
    report = {
        "generated_at": utc_now(),
        "ok": bool(accepted and turn_detected and returned_media and stopped),
        "url": url,
        "accepted": accepted,
        "turn_detected": turn_detected,
        "returned_media": returned_media,
        "stopped": stopped,
        "voice_frames": voice_frames,
        "silence_frames": silence_frames,
        "message_count": len(messages),
        "messages": messages,
        "safety_boundary": "Synthetic local websocket regression only. No phone provider, external call, or live routing is used.",
    }
    write_json(LATEST_REGRESSION, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a synthetic Twilio Media Streams regression against the local JVT audio bridge.")
    parser.add_argument("--url", default="ws://127.0.0.1:8761/twilio-media")
    parser.add_argument("--voice-frames", type=int, default=16)
    parser.add_argument("--silence-frames", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    args = parser.parse_args()
    report = asyncio.run(run_regression(args.url, args.voice_frames, args.silence_frames, args.timeout_seconds))
    print(json.dumps({
        "ok": report["ok"],
        "accepted": report["accepted"],
        "turn_detected": report["turn_detected"],
        "returned_media": report["returned_media"],
        "stopped": report["stopped"],
        "json_path": str(LATEST_REGRESSION),
    }))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
