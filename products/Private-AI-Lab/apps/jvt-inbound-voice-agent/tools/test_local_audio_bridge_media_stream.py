#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import audioop
import base64
import json
import statistics
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets


APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = APP_ROOT / "data" / "local-audio-bridge"
LATEST_REGRESSION = DATA_ROOT / "latest-regression.json"
DEFAULT_AUDIO = APP_ROOT / "voice-quality" / "normalized" / "quick-yes-take-01-20260701T192231Z.wav"
DEFAULT_EXPECTED = "workflow repetitive steps"
FRAME_SAMPLES = 160
SAMPLE_RATE = 8000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_pcm16_8khz_mono(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        pcm = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError(f"Expected PCM16 WAV, got sample width {width}")
    if channels == 2:
        pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    elif channels != 1:
        raise ValueError(f"Expected mono/stereo WAV, got {channels} channels")
    if rate != SAMPLE_RATE:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, SAMPLE_RATE, None)
    return pcm


def mulaw_payload(pcm16: bytes) -> str:
    return base64.b64encode(audioop.lin2ulaw(pcm16, 2)).decode("ascii")


def silence_payload() -> str:
    return base64.b64encode(b"\xff" * FRAME_SAMPLES).decode("ascii")


def audio_payloads(pcm16: bytes) -> list[str]:
    frame_bytes = FRAME_SAMPLES * 2
    frames = []
    for offset in range(0, len(pcm16), frame_bytes):
        chunk = pcm16[offset : offset + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk += b"\x00" * (frame_bytes - len(chunk))
        frames.append(mulaw_payload(chunk))
    return frames


def transcript_matches(transcript: str, expected_phrase: str) -> bool:
    actual = {word.lower() for word in transcript.split() if len(word) >= 4}
    expected = {word.lower() for word in expected_phrase.split() if len(word) >= 4}
    return bool(expected) and len(actual & expected) >= min(2, len(expected))


def percentile_95(values: list[float]) -> float:
    if not values:
        return 999.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


async def receive_until_mark(
    websocket: Any,
    messages: list[dict[str, Any]],
    timeout_seconds: float,
) -> tuple[dict[str, Any] | None, float]:
    started = time.perf_counter()
    completed: dict[str, Any] | None = None
    first_audio_seconds = 999.0
    while True:
        message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds))
        messages.append(message)
        if message.get("type") == "bridge.turn.completed":
            completed = message
        if message.get("event") == "media" and first_audio_seconds == 999.0:
            first_audio_seconds = time.perf_counter() - started
        if message.get("event") == "mark":
            return completed, first_audio_seconds


async def run_regression(
    url: str,
    audio_file: Path,
    expected_phrase: str,
    silence_frames: int,
    turns: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    turn_reports: list[dict[str, Any]] = []
    first_audio: list[float] = []
    stream_sid = "MT_RECORDED_JVT_LOCAL_BRIDGE"
    payloads = audio_payloads(load_pcm16_8khz_mono(audio_file))

    async with websockets.connect(url, open_timeout=timeout_seconds) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "event": "start",
                    "streamSid": stream_sid,
                    "start": {
                        "streamSid": stream_sid,
                        "callSid": "CA_RECORDED_JVT_LOCAL_BRIDGE",
                    },
                }
            )
        )
        messages.append(json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)))

        for _ in range(turns):
            for payload in payloads:
                await websocket.send(
                    json.dumps(
                        {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": payload},
                        }
                    )
                )
            for _ in range(silence_frames):
                await websocket.send(
                    json.dumps(
                        {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": silence_payload()},
                        }
                    )
                )
            completed, first_audio_seconds = await receive_until_mark(websocket, messages, timeout_seconds)
            if completed:
                turn_reports.append(completed)
            first_audio.append(first_audio_seconds)

        await websocket.send(json.dumps({"event": "stop", "streamSid": stream_sid}))
        while True:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds))
            messages.append(message)
            if message.get("status") == "stopped":
                break

    returned_media = [
        message
        for message in messages
        if message.get("event") == "media" and (message.get("media") or {}).get("payload")
    ]
    non_silent = False
    for message in returned_media:
        try:
            mulaw = base64.b64decode(message["media"]["payload"])
            non_silent = non_silent or audioop.rms(audioop.ulaw2lin(mulaw, 2), 2) > 100
        except Exception:
            continue

    transcripts = [str(turn.get("transcript") or "") for turn in turn_reports]
    timings = [turn.get("timings") or {} for turn in turn_reports]
    latency = {
        "stt_p95": round(percentile_95([float(item.get("stt") or 999) for item in timings]), 4),
        "router_p95": round(percentile_95([float(item.get("router") or 999) for item in timings]), 4),
        "tts_p95": round(percentile_95([float(item.get("tts") or 999) for item in timings]), 4),
        "first_audio_p95": round(percentile_95(first_audio), 4),
    }
    transcript_valid = bool(transcripts) and all(transcript_matches(item, expected_phrase) for item in transcripts)
    router_ok = bool(turn_reports) and all(bool(item.get("router_ok")) for item in turn_reports)
    multiple_turns = len(turn_reports) == turns and turns >= 2
    latency_ok = (
        latency["stt_p95"] <= 1.5
        and latency["router_p95"] <= 2.5
        and latency["tts_p95"] <= 0.8
        and latency["first_audio_p95"] <= 4.0
    )
    accepted = any(message.get("status") == "accepted" for message in messages)
    stopped = any(message.get("status") == "stopped" for message in messages)
    functional_ok = bool(
        accepted
        and transcript_valid
        and router_ok
        and non_silent
        and multiple_turns
        and stopped
    )
    report = {
        "generated_at": utc_now(),
        "ok": bool(functional_ok and latency_ok),
        "functional_ok": functional_ok,
        "latency_ok": latency_ok,
        "input_kind": "recorded-speech",
        "audio_file": str(audio_file),
        "expected_phrase": expected_phrase,
        "accepted": accepted,
        "transcript_valid": transcript_valid,
        "transcripts": transcripts,
        "router_ok": router_ok,
        "returned_non_silent_media": non_silent,
        "returned_media_frames": len(returned_media),
        "multiple_turns": multiple_turns,
        "completed_turns": len(turn_reports),
        "requested_turns": turns,
        "stopped": stopped,
        "latency_seconds": latency,
        "message_count": len(messages),
        "turn_reports": turn_reports,
        "safety_boundary": "Recorded local websocket regression only. No phone provider, external call, or live routing is used.",
    }
    write_json(LATEST_REGRESSION, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a recorded-speech Twilio Media Streams regression against the local JVT audio bridge.")
    parser.add_argument("--url", default="ws://127.0.0.1:8761/twilio-media")
    parser.add_argument("--audio-file", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--expected-phrase", default=DEFAULT_EXPECTED)
    parser.add_argument("--silence-frames", type=int, default=60)
    parser.add_argument("--turns", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=35.0)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=3.0)
    args = parser.parse_args()
    attempt_summaries: list[dict[str, Any]] = []
    report: dict[str, Any] = {}
    for attempt in range(1, max(1, args.attempts) + 1):
        report = asyncio.run(
            run_regression(
                args.url,
                args.audio_file,
                args.expected_phrase,
                args.silence_frames,
                args.turns,
                args.timeout_seconds,
            )
        )
        attempt_summaries.append(
            {
                "attempt": attempt,
                "ok": report["ok"],
                "functional_ok": report["functional_ok"],
                "latency_ok": report["latency_ok"],
                "latency_seconds": report["latency_seconds"],
            }
        )
        if report["ok"]:
            break
        if attempt < max(1, args.attempts):
            time.sleep(max(0.0, args.retry_delay_seconds))
    report["attempts_run"] = len(attempt_summaries)
    report["attempt_summaries"] = attempt_summaries
    write_json(LATEST_REGRESSION, report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "functional_ok": report["functional_ok"],
                "latency_ok": report["latency_ok"],
                "transcripts": report["transcripts"],
                "router_ok": report["router_ok"],
                "returned_non_silent_media": report["returned_non_silent_media"],
                "completed_turns": report["completed_turns"],
                "latency_seconds": report["latency_seconds"],
                "json_path": str(LATEST_REGRESSION),
            }
        )
    )
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
