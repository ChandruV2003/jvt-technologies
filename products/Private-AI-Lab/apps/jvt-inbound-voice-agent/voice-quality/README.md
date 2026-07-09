# JVT Voice Quality Evaluation

This folder is for consented JVT voice-quality experiments.

## Folders

- `samples/`: Chandru-approved raw recordings only.
- `scripts/`: test lines and scenario scripts.
- `renders/`: generated voice outputs from local/provider tests.
- `scorecards/`: side-by-side human review notes.

## Rules

- Do not store third-party voice samples here without explicit consent.
- Do not deploy any generated voice to live calls from this folder.
- Do not use generated voice for outbound calls.
- Keep AI disclosure in the call flow.
- Keep provider name, model name, date, input sample, and generated output documented in the scorecard.

## First Test Set

Use `runbooks/jvt-human-voice-quality-track.md` for the first script pack and scoring criteria.

## Local Recorder Panel

The M4 voice agent serves a private recorder at:

`http://127.0.0.1:8066/voice-quality`

It is also available through Tailscale HTTPS at:

`https://m4-mac-mini.tailee4a3f.ts.net/voice-quality`

Use the Tailscale URL from a Tailnet device or use KVM/localhost on the M4.
Browser microphone permissions require a secure context, so the Tailscale HTTPS
URL is the preferred non-KVM recording path.

The recorder page and recorder API are blocked from the public voice tunnel.
Uploads are allowed from localhost and approved Tailnet clients only.

Recording flow:

1. Open the recorder panel on the M4.
2. Click `Start mic`.
3. Record one script at a time.
4. Listen back before saving.
5. Save only clean takes with no background noise, clipping, or interruptions.

Preferred recording chain:

- Input: Universal Audio Volt 276 / UA-276.
- Mic: Shure SM7dB or the current high-quality vocal mic on Volt input 1.
- Browser target: the recorder requests 192 kHz, 24-bit, one-channel capture
  with echo cancellation, noise suppression, and automatic gain disabled.
- Verification: after `Start mic`, confirm the panel says `Universal Audio`,
  `Volt 276`, or `UA-276` under `Input device`. The browser-reported sample
  rate is shown under `Sample rate` and saved into the take metadata.
- Practical note: Chrome/macOS may grant 48 kHz even when 192 kHz is requested.
  Treat the displayed sample rate as the truth for that take.
- Guaranteed input-1-only path: run
  `voice-quality/tools/local-mac-volt-bridge.py` on the Mac that has the Volt
  connected. It records AVFoundation device `0` / Volt hardware input `1`,
  writes mono 24-bit WAV, and uploads the take to the M4 sample API over
  Tailscale.

Saved files:

- Audio: `voice-quality/samples/*.webm`, `.m4a`, `.ogg`, or `.wav`
- Metadata: matching `voice-quality/samples/*.json`
- Script pack: `voice-quality/scripts/chandru-style-script-pack.json`

Remote writes stay blocked unless `JVT_VOICE_RECORDER_ALLOW_REMOTE=1` is set
intentionally for a controlled private session.
