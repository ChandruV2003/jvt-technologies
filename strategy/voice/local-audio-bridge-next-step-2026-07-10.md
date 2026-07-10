# Local Audio Bridge Next Step

- Generated: `2026-07-10T02:17:51+00:00`
- Bridge health: `pipeline-draft`
- Bridge ready: `False`
- Voice live-ready: `False`
- Local bridge gate: `False`

## Required Build Steps

- `voice-bridge-agent`: replace contract-only bridge with real audio turn pipeline. Decode Twilio PCMU frames, buffer speech turns with VAD, transcribe locally, route text through the model router, synthesize reply audio, and encode outbound PCMU frames.
- `voice-bridge-agent`: select local STT backend. Prefer the lowest-latency local backend that can run on the M4 without cloud keys. Validate with recorded dental/JVT prompt samples before live routing.
- `voice-quality-agent`: select low-latency TTS path. Use the current voice samples for style direction, but do not deploy cloned voice audio until latency, consent, and disclosure wording are approved.
- `qa-agent`: add synthetic media-stream regression. Feed sample inbound frames through the websocket bridge and require health to report ready only after STT, model, TTS, and return-audio checks pass.

## Guardrail

Internal bridge-readiness work only. No provider credentials, live routing, or outbound calls are enabled.

Do not mark the bridge ready until health reports `ready=true` and the synthetic media-stream regression proves local STT, model response, TTS, and return audio.
