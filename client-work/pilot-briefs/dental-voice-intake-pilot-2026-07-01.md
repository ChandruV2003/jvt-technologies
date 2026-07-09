# Pilot Brief: Dental Office AI Voice Intake

Generated: 2026-07-01T19:33:25+00:00

Status: internal planning brief. Do not contact the prospect, enable live calls, connect paid phone-provider usage, process real patient data, or make service commitments from this file.

## Target Customer

A small dental office or specialty practice that receives scheduling, insurance, callback, and after-hours urgency calls.

## Pain / Demand

- Staff spend time collecting repeated details from callers.
- After-hours voicemails are often incomplete.
- New-patient, reschedule, insurance, and urgent-pain calls need different routing.
- Call notes need to be clear enough for staff to review without the AI making medical or scheduling commitments.

## Proposed Offer

A disclosed AI voice intake assistant that captures structured call packets for staff review.

Initial paid pilot scope:

1. Intake script: one question at a time, short, human-sounding, explicitly AI-disclosed.
2. Routing classifier: new patient, existing patient, reschedule, insurance question, urgent symptom, billing/admin, other.
3. Staff review packet: caller name, callback number, request type, urgency flag, preferred windows, insurance carrier name if volunteered, and transcript summary.
4. Safety handoff: no diagnosis, no medication advice, no final scheduling, no coverage confirmation.
5. QA loop: review call packets weekly and adjust prompts/scripts.

## Hard Boundaries

- Do not give dental, medical, medication, or emergency advice.
- Do not confirm insurance coverage.
- Do not book, cancel, or reschedule final appointments unless the office explicitly approves a controlled workflow later.
- Do not expose patient records or imply access to patient history.
- Keep the assistant disclosed as AI-assisted.
- Keep all real call handling disabled until provider, compliance, and operator approval gates are cleared.

## Agent Workflow Sketch

```text
Inbound call
  -> AI disclosure
  -> request type + caller details
  -> urgency/safety boundary check
  -> staff-review packet
  -> notification / dashboard item
  -> human callback or action
```

## Voice Quality Notes

- Use Chandru-approved voice samples only as internal style references.
- Do not replay raw samples directly as responses.
- Tune for natural cadence, quick turn-taking, and minimal filler.
- One or two natural pauses/fillers can mask latency, but the goal is fast, concise conversation.
- Tone should adapt to caller context: warmer for anxious/urgent callers, concise for scheduling/admin calls.

## Pricing Hypothesis

- Discovery/script map: $500-$1,000 fixed fee.
- Dry-run pilot build: $750-$1,500 fixed fee.
- Managed support: $300-$900/month depending on call volume, QA, and provider costs.

## Delivery Complexity

Medium. The intake workflow is achievable, but live phone latency, disclosure, provider cost, and patient-data expectations need careful gating.

## Major Risks

- Patient privacy expectations and health-adjacent communication.
- Caller may ask for medical advice.
- Latency or synthetic voice quality may reduce trust.
- Phone-provider/live-call costs can grow with usage.
- Office may expect scheduling-system integration too early.

## Next Validation Step

Collect prospect-specific workflow details before official outreach:

- office name and contact
- call categories they want handled
- after-hours expectations
- existing scheduling/phone system
- what the AI must never say
- what staff needs in the review packet
- how quickly staff responds to urgent items

## First Demo To Build

Use synthetic BrightPath-style calls and generate:

- new patient cleaning request packet
- existing patient reschedule packet
- urgent pain after-hours packet with safety handoff
- staff notification example
- dashboard review view
