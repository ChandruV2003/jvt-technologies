# Synthetic Demo Packet: Dental Voice Intake

Generated: 2026-07-09

Status: synthetic internal sales/demo artifact. This is not a live patient record, not medical advice, and not approved for live phone deployment.

## Demo Purpose

Show a dental office what JVT can produce after an AI-disclosed intake call: a clean staff-review packet, urgency boundaries, and a next-action queue that helps the front desk respond faster without letting the AI diagnose, schedule, or promise coverage.

## Synthetic Scenario A: New Patient Cleaning Request

### Caller Transcript Summary

Jordan Lee called after business hours asking about becoming a new patient and scheduling a cleaning. They recently moved to the area, prefer late afternoons, and asked whether the office accepts their insurance. The assistant collected callback details and explained that staff will confirm availability and insurance handling.

### Staff Review Packet

- Caller: Jordan Lee
- Callback: 555-0142
- Request type: New patient
- Urgency: Normal
- Preferred windows: Weekdays after 4 PM
- Insurance mentioned: Delta Dental, not verified
- Staff next action: Call back, confirm new-patient availability, collect full insurance details through the approved office process
- AI boundary used: Did not confirm coverage or book an appointment

### Suggested Staff Reply

Hi Jordan, this is BrightPath Dental returning your call. We can help with new-patient availability and collect your insurance details so our team can review them. What day this week works best for a quick callback?

## Synthetic Scenario B: Existing Patient Reschedule

### Caller Transcript Summary

Maria Gomez called to reschedule a hygiene appointment because of a work conflict. She asked whether next Friday morning was open. The assistant collected the preferred window and flagged the request for staff because the AI does not modify the schedule directly.

### Staff Review Packet

- Caller: Maria Gomez
- Callback: 555-0198
- Request type: Reschedule
- Urgency: Normal
- Preferred windows: Friday morning
- Existing appointment: Caller says it is currently next Tuesday at 2 PM
- Staff next action: Verify patient identity and appointment details, then offer approved reschedule options
- AI boundary used: Did not cancel or move the appointment

### Suggested Staff Reply

Hi Maria, we received your reschedule request. Before changing anything, we just need to verify the appointment details and then we can check Friday morning availability for you.

## Synthetic Scenario C: Urgent Pain After Hours

### Caller Transcript Summary

Anthony Brooks called after hours about tooth pain that started the same day. He asked whether he should take medication and whether it was an emergency. The assistant did not provide medical advice. It collected callback information, asked whether there were severe symptoms, and routed the packet as urgent staff review.

### Staff Review Packet

- Caller: Anthony Brooks
- Callback: 555-0164
- Request type: Urgent symptom
- Urgency: High staff review
- Severe symptoms volunteered: Caller did not report swelling of throat/face or trouble breathing during intake
- Staff next action: Call back using the office's urgent-care protocol
- AI boundary used: Did not diagnose, recommend medication, or decide emergency status

### Suggested Staff Reply

Hi Anthony, this is BrightPath Dental returning your urgent message. I’m going to ask a couple of safety questions and then route you using our office protocol.

## Review Queue Example

| Time | Caller | Type | Urgency | Status | Staff Owner |
| --- | --- | --- | --- | --- | --- |
| 7:42 PM | Anthony Brooks | Urgent symptom | High | Needs callback | Front desk / on-call rule |
| 6:18 PM | Jordan Lee | New patient | Normal | Needs callback | Front desk |
| 5:55 PM | Maria Gomez | Reschedule | Normal | Needs verification | Front desk |

## What JVT Is Selling Here

- A safer front-door intake layer for repeat calls.
- Better after-hours packets than voicemail alone.
- A staff dashboard queue with clear next actions.
- Guardrails that keep the AI from practicing dentistry, promising insurance coverage, or changing the schedule without office approval.

## Pilot Acceptance Criteria

- The assistant discloses it is AI-assisted.
- Every call becomes a staff-review packet.
- Urgent symptoms are escalated without medical advice.
- Staff can edit/reject summaries before any external follow-up.
- No live patient data is used until compliance and provider gates are approved.
