# Dental Office AI Voice Agent Pilot

## Target Customer

Small dental offices that miss calls, lose after-hours appointment requests, or spend staff time collecting the same basic scheduling details.

## Pain

- patients call when the front desk is busy or closed
- new-patient requests arrive without clean insurance, callback, or appointment-window details
- existing patients need reschedules and simple routing
- urgent calls need clear escalation without the AI giving medical advice

## Offer

A disclosed AI receptionist that answers inbound calls, captures minimum necessary intake details, classifies the request, and creates a staff review packet. It starts in dry-run and can move to live inbound calls only after the office approves disclosure, escalation, and data-handling rules.

## Pilot Scope

- configure dental-specific greeting and disclosure
- capture caller name, phone, email, request type, preferred callback window, and optional insurance carrier name
- route routine scheduling, reschedule, insurance/admin, and urgent/escalation requests into review packets
- run synthetic dry-run scenarios before any live call handling
- deliver a staff-facing intake report format

## Out Of Scope

- diagnosis, treatment, medication, or emergency medical advice
- final appointment booking without an approved scheduling integration
- payment collection
- outbound calls or SMS
- use of real patient data before privacy handling is approved

## Pricing Hypothesis

- setup: `$750-$1,500`
- monthly support: `$300-$750/mo`
- usage: pass-through phone/voice/model costs, quoted separately after provider selection

## Delivery Complexity

Medium. Dry-run setup is straightforward. Live calling requires provider configuration, public webhook, disclosure script, emergency routing, and privacy review.

## Major Risks

- HIPAA/PHI expectations
- caller thinks the AI is a human
- urgent patient issue is mishandled
- office expects final scheduling without system access
- phone provider and transcription costs

## Next Validation Step

Run the dental dry-run scenario pack, review the generated intake packets, then use the voice-agent pilot checklist before discussing live provider setup.

## Current Internal Assets

- dry-run app: `products/Private-AI-Lab/apps/jvt-inbound-voice-agent`
- scenario pack: `products/Private-AI-Lab/apps/jvt-inbound-voice-agent/demo-scenarios/dental-office-scenarios.json`
- checklist: `client-work/templates/voice-agent-pilot-checklist.md`
