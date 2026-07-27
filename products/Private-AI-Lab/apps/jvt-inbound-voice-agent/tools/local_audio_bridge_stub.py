#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import audioop
import base64
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


app = FastAPI(title="JVT Local Audio Bridge", version="0.2.0")
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = APP_ROOT / "data" / "local-audio-bridge"
LATEST_REGRESSION = DATA_ROOT / "latest-regression.json"
DEFAULT_STT_MODEL = "mlx-community/whisper-base.en-mlx-q4"
DEFAULT_ROUTER_URL = "http://127.0.0.1:8760"
FALLBACK_RESPONSE = "Thanks. I captured that for review. What is the best name and callback number for your request?"
FRAME_BYTES = 320
MULAW_FRAME_BYTES = 160
SAMPLE_RATE = 8000
_MLX_WHISPER: Any | None = None
_KEEPALIVE_TASK: asyncio.Task[Any] | None = None


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def load_latest_regression() -> dict[str, Any]:
    if not LATEST_REGRESSION.exists():
        return {"ok": False, "status": "missing"}
    try:
        return json.loads(LATEST_REGRESSION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "unreadable", "error": str(exc)}


def stt_model() -> str:
    return os.environ.get("JVT_LOCAL_AUDIO_BRIDGE_STT_MODEL", DEFAULT_STT_MODEL).strip()


def router_url() -> str:
    return os.environ.get("JVT_MODEL_ROUTER_URL", DEFAULT_ROUTER_URL).rstrip("/")


def stt_available() -> bool:
    return importlib.util.find_spec("mlx_whisper") is not None


def router_available() -> tuple[bool, str]:
    url = f"{router_url()}/health"
    try:
        response = httpx.get(
            url,
            timeout=float_env("JVT_LOCAL_AUDIO_BRIDGE_HEALTH_TIMEOUT", 8.0),
        )
        return response.status_code == 200, f"{response.status_code} {url}"
    except Exception as exc:
        return False, str(exc)


def regression_ready(regression: dict[str, Any]) -> bool:
    latency = regression.get("latency_seconds") if isinstance(regression.get("latency_seconds"), dict) else {}
    try:
        generated_at = datetime.fromisoformat(str(regression.get("generated_at") or "").replace("Z", "+00:00"))
        recent = (datetime.now(timezone.utc) - generated_at.astimezone(timezone.utc)).total_seconds() <= 86400
    except (TypeError, ValueError):
        recent = False
    return bool(
        regression.get("ok")
        and recent
        and regression.get("input_kind") == "recorded-speech"
        and regression.get("transcript_valid")
        and regression.get("router_ok")
        and regression.get("returned_non_silent_media")
        and regression.get("multiple_turns")
        and float(latency.get("stt_p95") or 999) <= 1.5
        and float(latency.get("router_p95") or 999) <= 2.5
        and float(latency.get("tts_p95") or 999) <= 0.8
        and float(latency.get("first_audio_p95") or 999) <= 4.0
    )


def component_status() -> dict[str, Any]:
    regression = load_latest_regression()
    router_ok, router_detail = router_available()
    say_path = shutil.which("say") or ""
    components = {
        "configured": truthy(os.environ.get("JVT_LOCAL_AUDIO_BRIDGE_READY", "0")),
        "stt_import": stt_available(),
        "stt_model": stt_model(),
        "router": router_ok,
        "router_detail": router_detail,
        "tts": bool(say_path),
        "tts_path": say_path,
        "regression": regression_ready(regression),
    }
    components["ready"] = bool(
        components["configured"]
        and components["stt_import"]
        and components["router"]
        and components["tts"]
        and components["regression"]
    )
    return components


def bridge_ready() -> bool:
    return bool(component_status().get("ready"))


def _load_mlx_whisper() -> Any:
    global _MLX_WHISPER
    if _MLX_WHISPER is None:
        import mlx_whisper

        _MLX_WHISPER = mlx_whisper
    return _MLX_WHISPER


def transcribe_pcm(pcm16: bytes) -> str:
    if not pcm16:
        return ""
    whisper_pcm, _ = audioop.ratecv(pcm16, 2, 1, SAMPLE_RATE, 16000, None)
    audio = np.frombuffer(whisper_pcm, dtype="<i2").astype(np.float32) / 32768.0
    result = _load_mlx_whisper().transcribe(
        audio,
        path_or_hf_repo=stt_model(),
        language="en",
        verbose=None,
        condition_on_previous_text=False,
        temperature=0.0,
    )
    return re.sub(r"\s+", " ", str((result or {}).get("text") or "")).strip()


def clean_model_response(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<\|.*?\|>", "", cleaned)
    cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"[*_#`]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return FALLBACK_RESPONSE
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return " ".join(sentences[:2])[:320].strip()


async def route_response(transcript: str) -> tuple[str, bool]:
    prompt = (
        "You are the disclosed AI intake assistant for JVT Technologies. "
        "Reply in one or two short natural sentences suitable for a phone call. "
        "Collect business workflow details and callback information. "
        "Do not diagnose, give legal or financial advice, confirm insurance, schedule appointments, "
        "quote final prices, make commitments, or claim to be human. "
        "If the request needs judgment, say a person will review it. "
        f"Caller said: {transcript}"
    )
    payload = {
        "task_type": "voice_intake",
        "messages": [
            {
                "role": "system",
                "content": "/no_think Be concise, calm, conversational, and review-first.",
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 45,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        async with httpx.AsyncClient(timeout=float_env("JVT_LOCAL_AUDIO_BRIDGE_ROUTER_TIMEOUT", 25.0)) as client:
            response = await client.post(f"{router_url()}/v1/chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") if isinstance(body.get("choices"), list) else []
        content = str((((choices[0] or {}).get("message") or {}).get("content") or "")) if choices else ""
        cleaned = clean_model_response(content)
        return cleaned, bool(content.strip())
    except Exception:
        return FALLBACK_RESPONSE, False


async def prewarm_router() -> tuple[bool, float]:
    started = time.perf_counter()
    payload = {
        "task_type": "voice_intake",
        "messages": [
            {"role": "system", "content": "/no_think Reply with one word."},
            {"role": "user", "content": "Ready?"},
        ],
        "stream": False,
        "temperature": 0.0,
        "max_tokens": 2,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        async with httpx.AsyncClient(timeout=float_env("JVT_LOCAL_AUDIO_BRIDGE_PREWARM_TIMEOUT", 15.0)) as client:
            response = await client.post(f"{router_url()}/v1/chat/completions", json=payload)
            response.raise_for_status()
        return True, time.perf_counter() - started
    except Exception:
        return False, time.perf_counter() - started


async def router_keepalive_loop() -> None:
    interval = max(60, int_env("JVT_LOCAL_AUDIO_BRIDGE_KEEPALIVE_SECONDS", 300))
    while True:
        if truthy(os.environ.get("JVT_LOCAL_AUDIO_BRIDGE_READY", "0")):
            await prewarm_router()
        await asyncio.sleep(interval)


@app.on_event("startup")
async def start_router_keepalive() -> None:
    global _KEEPALIVE_TASK
    if _KEEPALIVE_TASK is None or _KEEPALIVE_TASK.done():
        _KEEPALIVE_TASK = asyncio.create_task(router_keepalive_loop())


@app.on_event("shutdown")
async def stop_router_keepalive() -> None:
    global _KEEPALIVE_TASK
    if _KEEPALIVE_TASK is not None:
        _KEEPALIVE_TASK.cancel()
        _KEEPALIVE_TASK = None


def synthesize_pcmu_frames(text: str) -> list[str]:
    say_path = shutil.which("say")
    if not say_path:
        raise RuntimeError("macOS say command is unavailable")
    voice = os.environ.get("JVT_LOCAL_AUDIO_BRIDGE_TTS_VOICE", "Samantha").strip() or "Samantha"
    with tempfile.TemporaryDirectory(prefix="jvt-voice-bridge-") as temp:
        wav_path = Path(temp) / "response.wav"
        subprocess.run(
            [
                say_path,
                "-v",
                voice,
                "-o",
                str(wav_path),
                "--file-format=WAVE",
                "--data-format=LEI16@8000",
                text,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        with wave.open(str(wav_path), "rb") as handle:
            if handle.getnchannels() != 1 or handle.getsampwidth() != 2 or handle.getframerate() != SAMPLE_RATE:
                raise RuntimeError("TTS output is not 8 kHz mono PCM16")
            pcm16 = handle.readframes(handle.getnframes())
    mulaw = audioop.lin2ulaw(pcm16, 2)
    frames = []
    for offset in range(0, len(mulaw), MULAW_FRAME_BYTES):
        chunk = mulaw[offset : offset + MULAW_FRAME_BYTES]
        if len(chunk) < MULAW_FRAME_BYTES:
            chunk += b"\xff" * (MULAW_FRAME_BYTES - len(chunk))
        frames.append(base64.b64encode(chunk).decode("ascii"))
    if not frames:
        raise RuntimeError("TTS generated no audio frames")
    return frames


class BridgeSession:
    def __init__(self) -> None:
        self.stream_sid = ""
        self.call_sid = ""
        self.media_events = 0
        self.total_speech_frames = 0
        self.turn_count = 0
        self.max_rms = 0
        self.threshold = int_env("JVT_LOCAL_AUDIO_BRIDGE_RMS_THRESHOLD", 350)
        self.min_speech_frames = int_env("JVT_LOCAL_AUDIO_BRIDGE_MIN_SPEECH_FRAMES", 12)
        self.end_quiet_frames = int_env("JVT_LOCAL_AUDIO_BRIDGE_END_QUIET_FRAMES", 50)
        self.max_turn_frames = int_env("JVT_LOCAL_AUDIO_BRIDGE_MAX_TURN_FRAMES", 750)
        self._pcm = bytearray()
        self._speech_frames = 0
        self._quiet_frames = 0

    def reset_turn(self) -> None:
        self._pcm.clear()
        self._speech_frames = 0
        self._quiet_frames = 0

    def ingest_media(self, payload: str) -> dict[str, Any] | None:
        self.media_events += 1
        try:
            mulaw = base64.b64decode(payload, validate=True)
            pcm16 = audioop.ulaw2lin(mulaw, 2)
            rms = audioop.rms(pcm16, 2)
        except Exception as exc:
            return {"type": "bridge.error", "error": f"media_decode_failed: {exc}"}

        self.max_rms = max(self.max_rms, rms)
        if rms >= self.threshold:
            if not self._speech_frames:
                self._pcm.clear()
            self._speech_frames += 1
            self.total_speech_frames += 1
            self._quiet_frames = 0
            self._pcm.extend(pcm16)
        elif self._speech_frames:
            self._quiet_frames += 1
            self._pcm.extend(pcm16)

        frame_count = len(self._pcm) // FRAME_BYTES
        quiet_end = (
            self._speech_frames >= self.min_speech_frames
            and self._quiet_frames >= self.end_quiet_frames
        )
        max_end = frame_count >= self.max_turn_frames
        if quiet_end or max_end:
            pcm = bytes(self._pcm)
            self.turn_count += 1
            event = {
                "type": "bridge.turn.ready",
                "streamSid": self.stream_sid,
                "callSid": self.call_sid,
                "turn": self.turn_count,
                "media_events": self.media_events,
                "speech_frames": self._speech_frames,
                "quiet_frames": self._quiet_frames,
                "max_rms": self.max_rms,
                "pcm16": pcm,
            }
            self.reset_turn()
            return event
        return None


async def process_turn(turn: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    errors: list[str] = []
    pcm16 = bytes(turn.pop("pcm16"))

    stt_started = time.perf_counter()
    try:
        transcript = await asyncio.wait_for(
            asyncio.to_thread(transcribe_pcm, pcm16),
            timeout=float_env("JVT_LOCAL_AUDIO_BRIDGE_STT_TIMEOUT", 20.0),
        )
    except Exception as exc:
        transcript = ""
        errors.append(f"stt_failed: {exc}")
    stt_seconds = time.perf_counter() - stt_started

    router_started = time.perf_counter()
    response_text, router_ok = await route_response(transcript or "The caller audio could not be transcribed.")
    router_seconds = time.perf_counter() - router_started
    if not router_ok:
        errors.append("router_fallback_used")

    tts_started = time.perf_counter()
    try:
        audio_frames = await asyncio.wait_for(
            asyncio.to_thread(synthesize_pcmu_frames, response_text),
            timeout=float_env("JVT_LOCAL_AUDIO_BRIDGE_TTS_TIMEOUT", 12.0),
        )
    except Exception as exc:
        audio_frames = []
        errors.append(f"tts_failed: {exc}")
    tts_seconds = time.perf_counter() - tts_started

    return {
        **turn,
        "type": "bridge.turn.completed",
        "transcript": transcript,
        "response_text": response_text,
        "router_ok": router_ok,
        "audio_frame_count": len(audio_frames),
        "audio_frames": audio_frames,
        "timings": {
            "stt": round(stt_seconds, 4),
            "router": round(router_seconds, 4),
            "tts": round(tts_seconds, 4),
            "total": round(time.perf_counter() - started, 4),
        },
        "errors": errors,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    regression = load_latest_regression()
    components = component_status()
    ready = bool(components.get("ready"))
    return {
        "ok": ready,
        "ready": ready,
        "status": "ready" if ready else "validation-required",
        "generated_at": utc_now(),
        "contract": {
            "input": "Twilio Media Streams JSON frames.",
            "output": "Twilio-compatible 8 kHz PCMU media frames plus transcript/status events.",
            "audio_format": "8 kHz PCMU, 160-byte/20 ms outbound frames.",
        },
        "pipeline": {
            "vad": "energy-rms-multi-turn",
            "stt": stt_model(),
            "model": "JVT model router voice_intake route",
            "tts": f"macOS say/{os.environ.get('JVT_LOCAL_AUDIO_BRIDGE_TTS_VOICE', 'Samantha')}",
            "components": components,
            "latest_regression_ok": bool(regression.get("ok")),
            "latest_regression_generated_at": regression.get("generated_at"),
        },
        "safety_boundary": "Local validation only until configured=true and the recorded-speech accuracy, non-silent audio, multi-turn, and latency gates all pass. Provider routing stays disabled otherwise.",
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
                router_warm, prewarm_seconds = await prewarm_router()
                await websocket.send_json(
                    {
                        "type": "bridge.status",
                        "status": "accepted",
                        "streamSid": session.stream_sid,
                        "callSid": session.call_sid,
                        "ready": bridge_ready(),
                        "pipeline": "local-whisper-router-tts",
                        "router_warm": router_warm,
                        "prewarm_seconds": round(prewarm_seconds, 4),
                        "transcript": "Local audio bridge accepted the stream.",
                    }
                )
            elif event_name == "media":
                media = event.get("media") or {}
                response = session.ingest_media(str(media.get("payload") or ""))
                if response and response.get("type") == "bridge.error":
                    await websocket.send_json(response)
                elif response:
                    completed = await process_turn(response)
                    audio_frames = completed.pop("audio_frames")
                    await websocket.send_json(completed)
                    for payload in audio_frames:
                        await websocket.send_json(
                            {
                                "event": "media",
                                "streamSid": session.stream_sid,
                                "media": {"payload": payload},
                            }
                        )
                    await websocket.send_json(
                        {
                            "event": "mark",
                            "streamSid": session.stream_sid,
                            "mark": {"name": f"jvt-local-bridge-turn-{session.turn_count}"},
                        }
                    )
            elif event_name == "stop":
                await websocket.send_json(
                    {
                        "type": "bridge.status",
                        "status": "stopped",
                        "streamSid": session.stream_sid,
                        "callSid": session.call_sid,
                        "media_events": session.media_events,
                        "speech_frames": session.total_speech_frames,
                        "turn_count": session.turn_count,
                        "max_rms": session.max_rms,
                        "transcript": f"Local bridge stopped after {session.turn_count} completed turn(s).",
                    }
                )
                break
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "bridge.error", "error": str(exc)})
        except Exception:
            return
