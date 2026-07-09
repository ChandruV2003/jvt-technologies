# Dental Voice Agent Discovery Packet

Generated: 2026-07-09

Status: internal discovery packet. Do not send, quote, connect phone systems, or process real patient data without explicit approval.

## Target Customer

Small dental office, orthodontic office, oral surgery office, or specialty practice with repeated scheduling, insurance, callback, new-patient, and after-hours intake calls.

## Pain

- Front desk staff spend time collecting the same basic caller details.
- After-hours voicemails are incomplete and require callbacks.
- Urgent, non-urgent, insurance, scheduling, and billing calls need safer routing.
- A missed call can turn into a lost patient or delayed follow-up.

## Offer

A disclosed AI intake assistant that answers or simulates calls, asks one question at a time, captures structured intake packets, and hands everything to staff for review.

The assistant does not diagnose, give medical advice, confirm insurance coverage, finalize appointments, handle emergencies beyond directing urgent callers to appropriate emergency paths, or make commitments on behalf of the office.

## Discovery Questions

- What office name, address, phone number, and website should the demo use?
- What phone system is currently used?
- What call categories matter most: new patient, existing patient, emergency, insurance, billing, scheduling, cancellation, referral, records request?
- What are the exact handoff rules for emergencies or pain-related calls?
- What should the assistant never say?
- What information must be captured before staff can follow up?
- What business hours and after-hours rules should apply?
- Should the demo be text-only, simulated call, or real recorded voice walkthrough?
- Who reviews the packet internally before anything client-facing happens?

## First Low-Risk Pilot

Use synthetic calls only. Build three demo flows:

- New patient request: name, phone, preferred appointment window, insurance status, reason for visit, callback permission.
- Existing patient scheduling/cancellation: name, date of birth optional placeholder, reason, preferred time, urgency flag.
- After-hours urgent boundary: detect urgent language, avoid advice, capture callback details, direct emergency concerns to emergency services or the office's approved instructions.

Deliverable: one staff-review packet per simulated call, plus a short dashboard view of call category, missing info, urgency, and follow-up draft.

## Pricing Hypothesis

- Discovery/script map: $500-$1,000.
- Synthetic dry-run pilot: $750-$1,500.
- Managed support: $300-$900/month depending on call volume, QA, and reporting.

## Delivery Complexity

Medium. The intake product is feasible now as a simulated/demo workflow. Live calls require stricter gating around disclosure, patient-data handling, latency, provider costs, and emergency language.

## Risks

- Patient privacy and health-adjacent communication.
- Caller asks for dental, medical, medication, or emergency advice.
- Synthetic voice quality reduces trust.
- Prospect expects full scheduling-system integration too early.
- Staff may distrust the assistant if packets are noisy or too verbose.

## Demo Build Checklist

- Use only synthetic patient data.
- Include explicit AI disclosure.
- Keep human review before staff follow-up.
- Create three synthetic call transcripts.
- Generate three intake packets.
- Add a "never say" rules section.
- Add emergency-language boundary copy.
- Add one-page setup/pricing sheet.

## Next Validation Step

Get the real dental prospect's office name, best contact, phone system, and top three call categories. Then generate a branded synthetic demo packet and a concise reply email.

