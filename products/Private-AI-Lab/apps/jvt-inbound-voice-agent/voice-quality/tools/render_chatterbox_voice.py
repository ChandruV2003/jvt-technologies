#!/usr/bin/env python3
"""Render an internal JVT voice-clone test sample with Chatterbox TTS.

This is for consented internal quality work only. It must not be wired into
live calls, public demos, or outbound automation without a separate approval
gate and human review.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import torch
import torchaudio
from chatterbox.tts import ChatterboxTTS


ROOT = Path(os.environ.get("JVT_VOICE_RENDER_LAB", "/Users/chandruv/.jvt/voice-render-lab"))
NORMALIZED_DIR = ROOT / "normalized"
RENDERS_DIR = ROOT / "renders"
SCORECARDS_DIR = ROOT / "scorecards"

DEFAULT_REFERENCE = NORMALIZED_DIR / "warm-intro-take-01-20260701T191733Z.wav"
DEFAULT_TEXT = (
    "Hey, this is Chandru from JVT Technologies. "
    "I can walk through the workflow, show the review packet, "
    "and keep the next step simple."
)


def pick_device() -> str:
    override = os.environ.get("JVT_CHATTERBOX_DEVICE")
    if override:
        return override
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> int:
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    SCORECARDS_DIR.mkdir(parents=True, exist_ok=True)

    reference_path = Path(os.environ.get("JVT_CHATTERBOX_REFERENCE", DEFAULT_REFERENCE))
    if not reference_path.exists():
        raise FileNotFoundError(f"reference sample not found: {reference_path}")

    text = os.environ.get("JVT_CHATTERBOX_TEXT", DEFAULT_TEXT)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    render_path = RENDERS_DIR / f"jvt-chandru-chatterbox-internal-{stamp}.wav"
    metadata_path = render_path.with_suffix(".json")

    device = pick_device()
    params = {
        "exaggeration": float(os.environ.get("JVT_CHATTERBOX_EXAGGERATION", "0.35")),
        "cfg_weight": float(os.environ.get("JVT_CHATTERBOX_CFG_WEIGHT", "0.5")),
        "temperature": float(os.environ.get("JVT_CHATTERBOX_TEMPERATURE", "0.7")),
        "repetition_penalty": float(os.environ.get("JVT_CHATTERBOX_REPETITION_PENALTY", "1.2")),
        "min_p": float(os.environ.get("JVT_CHATTERBOX_MIN_P", "0.05")),
        "top_p": float(os.environ.get("JVT_CHATTERBOX_TOP_P", "1.0")),
    }

    model = ChatterboxTTS.from_pretrained(device)
    wav = model.generate(
        text,
        audio_prompt_path=str(reference_path),
        repetition_penalty=params["repetition_penalty"],
        min_p=params["min_p"],
        top_p=params["top_p"],
        exaggeration=params["exaggeration"],
        cfg_weight=params["cfg_weight"],
        temperature=params["temperature"],
    )

    if wav.ndim == 1:
        wav = wav.unsqueeze(0)
    wav = wav.detach().cpu().float()

    peak = float(wav.abs().max().item()) if wav.numel() else 0.0
    if peak > 0.99:
        wav = wav * (0.98 / peak)

    sample_rate = int(getattr(model, "sr", 24000))
    torchaudio.save(str(render_path), wav, sample_rate)

    metadata = {
        "created_at": stamp,
        "tool": "chatterbox-tts",
        "purpose": "internal voice quality render only",
        "device": device,
        "sample_rate": sample_rate,
        "reference_path": str(reference_path),
        "render_path": str(render_path),
        "text": text,
        "params": params,
        "safety_note": (
            "Consent-based internal render. Not approved for outbound calls, "
            "public publishing, or impersonation use."
        ),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
