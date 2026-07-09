#!/usr/bin/env python3

from __future__ import annotations

import argparse
import audioop
import json
import math
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_audio(meta_path: Path) -> Path | None:
    for suffix in (".webm", ".wav", ".m4a", ".ogg", ".flac", ".mp3"):
        candidate = meta_path.with_suffix(suffix)
        if candidate.exists():
            return candidate
    return None


def ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg
    except Exception as exc:  # pragma: no cover - surfaced in report
        raise SystemExit(f"imageio_ffmpeg is required. Run tools/setup_voice_quality_tooling.sh first. Error: {exc}") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def convert_to_wav(ffmpeg: str, source: Path, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        "48000",
        "-sample_fmt",
        "s16",
        str(target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stderr": result.stderr.strip(),
        "target": str(target),
    }


def analyze_wav(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frame_rate = wav.getframerate()
        frame_count = wav.getnframes()
        duration = frame_count / frame_rate if frame_rate else 0
        frames = wav.readframes(frame_count)

    rms = audioop.rms(frames, sample_width) if frames else 0
    peak = audioop.max(frames, sample_width) if frames else 0
    max_possible = float((2 ** (8 * sample_width - 1)) - 1) if sample_width else 1.0
    peak_dbfs = 20 * math.log10(max(peak, 1) / max_possible)
    rms_dbfs = 20 * math.log10(max(rms, 1) / max_possible)
    clipping_risk = peak >= max_possible * 0.98
    return {
        "channels": channels,
        "sample_width_bytes": sample_width,
        "sample_rate": frame_rate,
        "frames": frame_count,
        "duration_seconds": round(duration, 3),
        "rms_dbfs": round(rms_dbfs, 2),
        "peak_dbfs": round(peak_dbfs, 2),
        "clipping_risk": clipping_risk,
    }


def quality_notes(analysis: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    duration = float(analysis.get("duration_seconds") or 0)
    rms = float(analysis.get("rms_dbfs") or -120)
    peak = float(analysis.get("peak_dbfs") or -120)
    if duration < 2:
        notes.append("very short take")
    if rms < -35:
        notes.append("quiet average level")
    if peak > -1:
        notes.append("near clipping")
    if analysis.get("clipping_risk"):
        notes.append("clipping risk")
    return notes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    root = Path(args.root).resolve()
    samples_root = root / "samples"
    normalized_root = root / "normalized"
    scorecards_root = root / "scorecards"
    scorecards_root.mkdir(parents=True, exist_ok=True)

    ffmpeg = ffmpeg_path()
    generated_at = utc_now()
    sample_reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for meta_path in sorted(samples_root.glob("*.json")):
        meta = load_json(meta_path)
        source = find_audio(meta_path)
        if not source:
            failures.append({"metadata": str(meta_path), "reason": "missing audio"})
            continue
        target = normalized_root / f"{meta_path.stem}.wav"
        conversion = convert_to_wav(ffmpeg, source, target)
        if not conversion["ok"]:
            failures.append({"metadata": str(meta_path), "source": str(source), "conversion": conversion})
            continue
        analysis = analyze_wav(target)
        sample_reports.append({
            "script_id": meta.get("script_id") or meta_path.stem,
            "script_title": meta.get("script_title") or meta_path.stem,
            "category": meta.get("script_category") or "",
            "source_audio": str(source),
            "normalized_wav": str(target),
            "source_bytes": source.stat().st_size,
            "normalized_bytes": target.stat().st_size,
            "recorded_at": meta.get("recorded_at"),
            "input_device": meta.get("input_device"),
            "analysis": analysis,
            "quality_notes": quality_notes(analysis),
        })

    total_duration = round(sum(item["analysis"]["duration_seconds"] for item in sample_reports), 3)
    report = {
        "generated_at": generated_at,
        "ok": not failures and bool(sample_reports),
        "ffmpeg": ffmpeg,
        "sample_count": len(sample_reports),
        "failure_count": len(failures),
        "total_duration_seconds": total_duration,
        "total_duration_minutes": round(total_duration / 60, 2),
        "normalized_root": str(normalized_root),
        "samples": sample_reports,
        "failures": failures,
        "next_step": "Use normalized WAVs for a controlled local TTS/voice-render experiment, then compare generated renders against these source samples before any demo usage.",
        "safety_boundary": "Internal consented evaluation only. No live calls, outbound calls, public release, or undisclosed voice impersonation.",
    }

    report_json = scorecards_root / f"voice-normalization-scorecard-{datetime.now(timezone.utc).date().isoformat()}.json"
    report_md = scorecards_root / f"voice-normalization-scorecard-{datetime.now(timezone.utc).date().isoformat()}.md"
    report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Voice Normalization Scorecard",
        "",
        f"Generated: {generated_at}",
        "",
        "Status: internal consented evaluation only. No live/demo voice deployment from this artifact.",
        "",
        "## Summary",
        "",
        f"- Normalized samples: `{len(sample_reports)}`",
        f"- Failures: `{len(failures)}`",
        f"- Total source speech duration: `{report['total_duration_minutes']}` minutes",
        f"- Normalized output: `{normalized_root}`",
        "",
        "## Per-Sample Checks",
        "",
    ]
    for item in sample_reports:
        notes = ", ".join(item["quality_notes"]) if item["quality_notes"] else "ok"
        analysis = item["analysis"]
        lines.append(
            f"- `{item['script_id']}`: {analysis['duration_seconds']}s, "
            f"RMS {analysis['rms_dbfs']} dBFS, peak {analysis['peak_dbfs']} dBFS, notes: {notes}"
        )
    if failures:
        lines.extend(["", "## Failures", ""])
        for failure in failures:
            lines.append(f"- `{failure.get('metadata')}`: {failure.get('reason') or failure.get('conversion', {}).get('stderr')}")
    lines.extend([
        "",
        "## Next Step",
        "",
        report["next_step"],
        "",
        f"Safety boundary: {report['safety_boundary']}",
        "",
    ])
    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "sample_count": len(sample_reports), "failure_count": len(failures), "report_json": str(report_json), "report_md": str(report_md)}, indent=2))


if __name__ == "__main__":
    main()
