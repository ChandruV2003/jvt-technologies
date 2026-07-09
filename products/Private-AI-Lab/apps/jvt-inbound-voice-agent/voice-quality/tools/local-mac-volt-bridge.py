#!/usr/bin/env python3
"""Local Volt 276 -> M4 JVT voice-quality bridge.

Records consented Chandru voice samples from this Mac's AVFoundation input and
uploads them to the M4 voice-quality API over Tailscale.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
import re

API_BASE = os.environ.get("JVT_VOICE_API_BASE", "https://m4-mac-mini.tailee4a3f.ts.net").rstrip("/")
DEFAULT_DEVICE = os.environ.get("JVT_VOICE_AVFOUNDATION_DEVICE", "0")
DEFAULT_RATE = int(os.environ.get("JVT_VOICE_SAMPLE_RATE", "192000"))
DEFAULT_SECONDS = int(os.environ.get("JVT_VOICE_SECONDS", "12"))
DEFAULT_INPUT_CHANNEL = int(os.environ.get("JVT_VOICE_INPUT_CHANNEL", "1"))


def fetch_json(path: str) -> dict:
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def upload(script_id: str, wav_path: Path, metadata: dict) -> dict:
    query = urllib.parse.urlencode({"mime_type": "audio/wav"})
    url = f"{API_BASE}/api/voice-quality/samples/{urllib.parse.quote(script_id)}?{query}"
    data = wav_path.read_bytes()
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "audio/wav")
    request.add_header("X-JVT-Input-Device", metadata.get("input_device", "Volt 276"))
    request.add_header("X-JVT-Audio-Settings", json.dumps(metadata, separators=(",", ":")))
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def list_audio_devices() -> str:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.stdout


def parse_input_sample_rate(ffmpeg_output: str) -> int | None:
    input_seen = False
    for line in ffmpeg_output.splitlines():
        if line.startswith("Input #0"):
            input_seen = True
            continue
        if input_seen and "Audio:" in line:
            match = re.search(r"Audio:.*?\\b(\\d+) Hz\\b", line)
            if match:
                return int(match.group(1))
    return None


def record(device: str, input_channel: int, seconds: int, rate: int, out_path: Path) -> dict:
    if input_channel < 1:
        raise SystemExit("--input-channel must be 1 or higher")
    # AVFoundation exposes the Volt 276 as one stereo device. The SM7dB is on
    # hardware input 1, so keep channel 1 only instead of downmixing both inputs.
    channel_index = input_channel - 1
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-f",
        "avfoundation",
        "-i",
        f":{device}",
        "-t",
        str(seconds),
        "-filter:a",
        f"pan=mono|c0=c{channel_index}",
        "-ar",
        str(rate),
        "-c:a",
        "pcm_s24le",
        str(out_path),
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    print(proc.stdout)
    return {
        "ffmpeg_observed_input_sample_rate_hz": parse_input_sample_rate(proc.stdout),
        "ffmpeg_output": proc.stdout[-4000:],
    }


def choose_script(status: dict, script_id: str | None) -> dict:
    scripts = status.get("scripts") or []
    if script_id:
        for script in scripts:
            if script.get("id") == script_id:
                return script
        raise SystemExit(f"Unknown script_id: {script_id}")
    for index, script in enumerate(scripts, 1):
        print(f"{index:02d}. {script['id']} - {script['title']}")
    choice = input("Script number or id: ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(scripts):
            return scripts[idx]
    for script in scripts:
        if script.get("id") == choice:
            return script
    raise SystemExit("Invalid script selection")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Volt 276 voice samples and upload to M4 JVT voice-quality API.")
    parser.add_argument("--list-devices", action="store_true", help="List AVFoundation devices and exit.")
    parser.add_argument("--script-id", help="Script id to record, e.g. warm-intro.")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="AVFoundation audio device index. Volt 276 is usually 0 on this Mac.")
    parser.add_argument("--input-channel", type=int, default=DEFAULT_INPUT_CHANNEL, help="Volt hardware input channel to keep. SM7dB is on input 1.")
    parser.add_argument("--seconds", type=int, default=DEFAULT_SECONDS, help="Recording duration.")
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE, help="Output sample rate to request/write.")
    parser.add_argument("--dry-run", action="store_true", help="Record only; do not upload.")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not installed or not on PATH")

    if args.list_devices:
        print(list_audio_devices())
        return 0

    status = fetch_json("/api/voice-quality/status")
    if not status.get("write_allowed"):
        raise SystemExit("M4 recorder API is not write-enabled from this Mac/Tailnet.")

    script = choose_script(status, args.script_id)
    print("\nRead this exactly/naturally:")
    print("-" * 72)
    print(script["text"])
    print("-" * 72)
    input(f"Press Enter, then start speaking. Recording starts immediately for {args.seconds}s. ")

    timestamp = time.strftime("%Y%m%dT%H%M%S")
    out_path = Path(tempfile.gettempdir()) / f"jvt-{script['id']}-{timestamp}.wav"
    print(f"Recording from AVFoundation audio device :{args.device}, hardware input {args.input_channel}, at requested {args.rate} Hz...")
    capture_info = record(args.device, args.input_channel, args.seconds, args.rate, out_path)
    print(f"Recorded: {out_path} ({out_path.stat().st_size} bytes)")

    metadata = {
        "input_device": "Volt 276 via AVFoundation device 0" if args.device == "0" else f"AVFoundation audio device {args.device}",
        "input_channel": args.input_channel,
        "channel_filter": f"pan=mono|c0=c{args.input_channel - 1}",
        "capture_path": "local-mac-ffmpeg-tailnet-bridge",
        "requested_output_sample_rate_hz": args.rate,
        "observed_input_sample_rate_hz": capture_info.get("ffmpeg_observed_input_sample_rate_hz"),
        "channels": 1,
        "codec": "pcm_s24le",
        "duration_seconds": args.seconds,
        "local_temp_path": str(out_path),
        "note": "AVFoundation input rate is the real device stream rate; output rate may be resampled by ffmpeg.",
    }
    if args.dry_run:
        print("Dry-run only; not uploaded.")
        return 0

    payload = upload(script["id"], out_path, metadata)
    print(f"Uploaded: take {payload.get('take_number')} -> {payload.get('audio_path')}")
    print(f"Metadata: {payload.get('metadata_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
