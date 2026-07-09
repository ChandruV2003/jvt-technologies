#!/usr/bin/env python3
"""Write a basic technical scorecard for the latest JVT voice render."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import torch
import torchaudio


ROOT = Path("/Users/chandruv/.jvt/voice-render-lab")
RENDERS_DIR = ROOT / "renders"
SCORECARDS_DIR = ROOT / "scorecards"


def dbfs(rms: float) -> float:
    if rms <= 0:
        return float("-inf")
    return 20.0 * math.log10(rms)


def load_audio(path: Path) -> tuple[torch.Tensor, int]:
    wav, sr = torchaudio.load(str(path))
    if wav.ndim == 2 and wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    return wav.float(), int(sr)


def stats(path: Path) -> dict[str, float | int | str]:
    wav, sr = load_audio(path)
    flat = wav.flatten()
    duration = float(flat.numel() / sr) if sr else 0.0
    peak = float(flat.abs().max().item()) if flat.numel() else 0.0
    rms = float(torch.sqrt(torch.mean(flat * flat)).item()) if flat.numel() else 0.0
    silence_ratio = float((flat.abs() < 0.01).float().mean().item()) if flat.numel() else 1.0
    if flat.numel() > 1:
        zcr = float(((flat[:-1] * flat[1:]) < 0).float().mean().item())
    else:
        zcr = 0.0
    return {
        "path": str(path),
        "sample_rate": sr,
        "duration_seconds": round(duration, 3),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "rms_dbfs": round(dbfs(rms), 2) if rms > 0 else "-inf",
        "silence_ratio": round(silence_ratio, 4),
        "zero_crossing_rate": round(zcr, 6),
    }


def latest_render() -> Path:
    renders = sorted(RENDERS_DIR.glob("jvt-chandru-chatterbox-internal-*.wav"))
    if not renders:
        raise FileNotFoundError(f"no render WAVs found in {RENDERS_DIR}")
    return renders[-1]


def find_reference(render_path: Path) -> Path | None:
    meta_path = render_path.with_suffix(".json")
    if not meta_path.exists():
        return None
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    ref = Path(metadata.get("reference_path", ""))
    return ref if ref.exists() else None


def pass_fail(render_stats: dict[str, float | int | str]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    duration = float(render_stats["duration_seconds"])
    peak = float(render_stats["peak"])
    rms_db = float(render_stats["rms_dbfs"]) if render_stats["rms_dbfs"] != "-inf" else -999.0
    silence_ratio = float(render_stats["silence_ratio"])

    if duration < 3.0 or duration > 45.0:
        failures.append("duration outside expected test-render range")
    if peak < 0.03:
        failures.append("render level appears too low")
    if peak > 0.99:
        failures.append("render may be clipped")
    if rms_db < -45.0 or rms_db > -8.0:
        failures.append("average loudness outside rough speech range")
    if silence_ratio > 0.65:
        failures.append("too much near-silence for the prompt")

    return not failures, failures


def write_scorecard(render_path: Path) -> dict:
    SCORECARDS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reference_path = find_reference(render_path)
    render_stats = stats(render_path)
    reference_stats = stats(reference_path) if reference_path else None
    ok, failures = pass_fail(render_stats)

    report = {
        "created_at": stamp,
        "purpose": "internal JVT voice render technical QA",
        "render": render_stats,
        "reference": reference_stats,
        "technical_pass": ok,
        "failures": failures,
        "limits": [
            "This scorecard only checks file/level/silence basics.",
            "Manual listening is still required before any demo use.",
            "This render is not approved for live calls or public publishing.",
        ],
    }

    json_path = SCORECARDS_DIR / f"chatterbox-render-scorecard-{stamp}.json"
    md_path = SCORECARDS_DIR / f"chatterbox-render-scorecard-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    md = [
        "# Chatterbox Render Scorecard",
        "",
        f"- Created: `{stamp}`",
        f"- Render: `{render_stats['path']}`",
        f"- Reference: `{reference_stats['path'] if reference_stats else 'not found'}`",
        f"- Technical pass: `{ok}`",
        "",
        "## Render Stats",
        "",
        f"- Duration: `{render_stats['duration_seconds']}` seconds",
        f"- Sample rate: `{render_stats['sample_rate']}` Hz",
        f"- Peak: `{render_stats['peak']}`",
        f"- RMS dBFS: `{render_stats['rms_dbfs']}`",
        f"- Silence ratio: `{render_stats['silence_ratio']}`",
        f"- Zero crossing rate: `{render_stats['zero_crossing_rate']}`",
        "",
        "## Failures",
        "",
    ]
    md.extend([f"- {failure}" for failure in failures] or ["- None"])
    md.extend(
        [
            "",
            "## Limits",
            "",
            "- Basic technical QA only; manual listening is still required.",
            "- Internal consented voice-quality work only.",
            "- Not approved for outbound calls, public demos, or impersonation use.",
            "",
        ]
    )
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "technical_pass": ok}, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("render", nargs="?", type=Path)
    args = parser.parse_args()
    write_scorecard(args.render or latest_render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
