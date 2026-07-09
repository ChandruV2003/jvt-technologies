# JVT Inbound Voice Agent

Inbound-only receptionist scaffold for JVT Technologies LLC.

This app is intentionally narrow:

- answer inbound calls only
- disclose that the caller is speaking with JVT's AI assistant
- answer basic questions about JVT's private AI/document-workflow services
- collect structured lead details for human follow-up
- write call intake packets locally on the M4 Mac Mini
- avoid legal, tax, financial, or binding business commitments

It does not place outbound calls.

## Runtime

The app uses the existing Python/FastAPI stack already present on the M4. No Node runtime is required.

Default local URL:

- `http://127.0.0.1:8066`

Important endpoints:

- `GET /health`
- `GET /api/status`
- `GET /api/intake`
- `POST /api/test-intake`
- `POST /twilio/inbound`
- `WebSocket /twilio/media-stream`

## Run Locally

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/jvt-inbound-voice-agent
cp .env.example .env.local
./tools/run_voice_agent.sh
```

Dry-run mode is safe and is the default. It lets the webhook accept calls, show the disclosure, and create local intake records without connecting live audio to OpenAI.

## Install As M4 Service

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/jvt-inbound-voice-agent/tools/install_launch_agent.sh
```

Live mode requires:

- `OPENAI_API_KEY`
- `JVT_VOICE_DRY_RUN=0`
- `JVT_VOICE_PUBLIC_BASE_URL=https://voice.jvt-technologies.com` or another public HTTPS hostname
- `JVT_VOICE_PHONE_PROVIDER_CONFIGURED=1` after the phone provider webhook is actually pointed at this app
- a Twilio number or equivalent SIP/voice provider configured to call `POST /twilio/inbound`

The app reports `live-ready` only when all live gates are true:

- OpenAI API key is present
- public base URL starts with `https://`
- derived media stream URL starts with `wss://`
- dry-run is disabled
- phone-provider configuration has been explicitly marked complete

Until then, `/twilio/inbound` stays safe for dry-run validation and returns a setup-mode disclosure.

## Phone Provider Shape

The current scaffold returns TwiML for Twilio:

1. Twilio receives an inbound call.
2. Twilio requests `POST /twilio/inbound`.
3. The app discloses that this is an AI assistant.
4. Twilio connects media to `WebSocket /twilio/media-stream`.
5. The app bridges caller audio to OpenAI Realtime and streams assistant audio back.
6. The app saves a local intake record for review.

## Operating Boundary

The receptionist can:

- describe JVT's private document assistant, workflow automation, intake triage, and AI implementation services
- collect caller name, company, email, phone, workflow pain, timeline, and callback preference
- explain that Chandru or JVT will review and respond

The receptionist cannot:

- give legal, tax, financial, medical, or investment advice
- claim to be a human
- quote binding prices beyond public starting points
- accept contracts, payments, or client confidential documents over the phone
- make outbound sales calls
