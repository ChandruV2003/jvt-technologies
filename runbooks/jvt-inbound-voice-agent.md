# JVT Inbound Voice Agent Runbook

## Purpose

The voice agent is an inbound receptionist for JVT Technologies LLC. It should help callers understand what JVT does, collect lead details, and produce a reviewable intake packet.

It is not an outbound sales dialer.

## Current Implementation

- App path: `products/Private-AI-Lab/apps/jvt-inbound-voice-agent`
- Local port: `8066`
- Local health: `http://127.0.0.1:8066/health`
- Status: `http://127.0.0.1:8066/api/status`
- Intake packets: `products/Private-AI-Lab/apps/jvt-inbound-voice-agent/data/intake`
- Call records: `products/Private-AI-Lab/apps/jvt-inbound-voice-agent/data/calls`
- Voice quality track: `runbooks/jvt-human-voice-quality-track.md`
- Productization runbook: `runbooks/jvt-voice-agent-productization.md`

The app defaults to dry-run mode until a real public webhook and OpenAI key are configured.

## Manual Setup Needed Before Live Calls

1. Choose the phone provider path.
2. Buy or assign a JVT business phone number.
3. Point inbound calls to `POST /twilio/inbound`.
4. Expose the voice agent over public HTTPS/WSS, not just Tailscale.
5. Add `OPENAI_API_KEY` and set `JVT_VOICE_DRY_RUN=0`.
6. Place a test call and confirm the agent discloses that it is an AI assistant.
7. Confirm intake JSON files are created after calls.

## Dental Office Pilot Path

Use the dental vertical only as a dry-run or explicitly approved live pilot.

- Scenario pack:
  `products/Private-AI-Lab/apps/jvt-inbound-voice-agent/demo-scenarios/dental-office-scenarios.json`
- Pilot brief:
  `client-work/pilot-briefs/dental-office-voice-agent-pilot-2026-06-30.md`
- Pilot checklist:
  `client-work/templates/voice-agent-pilot-checklist.md`

Dental calls are high-risk because they can involve patient information,
appointment urgency, and medical-advice requests. The assistant may capture and
route basic details, but must not diagnose, advise on medication, promise
treatment, or finalize scheduling unless the office approves that exact
integration and script.

## Required Behavior

- Start with disclosure: caller is speaking with JVT's AI assistant.
- Keep answers short and practical.
- Ask one question at a time.
- Repeat back names, emails, phone numbers, and appointment details for confirmation.
- Escalate anything sensitive or uncertain to Chandru.

## Forbidden Behavior

- No outbound calling.
- No legal, tax, financial, medical, or investment advice.
- No pretending to be human.
- No binding quotes, contracts, payment commitments, or delivery promises.
- No accepting confidential client documents over the phone.

## Voice Quality Direction

The voice can be tuned toward Chandru's cadence and phrasing only with
Chandru-approved samples and clear AI disclosure. Do not deploy a cloned or
high-similarity voice path until the voice quality track has reviewed multiple
side-by-side samples and confirmed consent, disclosure, fallback behavior, and
human handoff language.
