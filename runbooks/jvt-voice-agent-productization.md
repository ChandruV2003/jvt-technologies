# JVT Voice Agent Productization Runbook

This is the repeatable path for turning an inbound voice-agent request into a scoped JVT pilot.

## Intake To Pilot Flow

1. Capture the lead in the inbox or client registry.
2. Identify vertical, caller types, and risk class.
3. Create a local client workspace with `client-work/tools/new_voice_agent_pilot.sh`.
4. Fill `01-intake/voice-agent-pilot-checklist.md`.
5. Build or select a vertical scenario pack.
6. Run dry-run scenarios against the local voice app.
7. Review generated intake packets.
8. Draft SOW and privacy/data handling addendum.
9. Only after approval, configure phone provider, public webhook, and live-call settings.

## Automation Boundary

The system may autonomously:

- create local workspaces
- generate dry-run scenarios
- run dry-run intake tests
- draft checklists, SOWs, and implementation notes
- summarize risk and next actions

The system must not autonomously:

- buy phone numbers
- connect live phone providers
- accept patient/client confidential data
- publish or change DNS/webhook routing for live calls
- make medical, legal, tax, financial, or investment claims
- send outbound calls, texts, or third-party emails
- quote binding pricing or sign agreements

## Vertical Risk Classes

- low risk: contractor, property manager, general service scheduling
- medium risk: CPA, law, insurance, financial admin, sensitive document offices
- high risk: dental, medical, mental health, elder care, legal advice-heavy workflows

High-risk verticals can still use the product, but only with tighter scripts, disclosure, minimum-data capture, and explicit escalation language.

## Dental Office First-Pass Scope

Start with routine intake and callback routing. Do not start with final scheduling, treatment questions, payment collection, or patient-specific advice.
