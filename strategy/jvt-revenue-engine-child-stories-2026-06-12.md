# JVT Revenue Engine Child Stories

Updated: 2026-06-12

Purpose: convert the strongest current lanes into queue-ready internal specs with a clear owner, proof target, and stop point.

## Summary Table

| Story ID | Offer lane | Queue owner | Why now | Status after this epic |
| --- | --- | --- | --- | --- |
| `REV-EPIC-01` | Workflow cleanup pilot package | Epic agent | fastest fixed-scope cash lane | advanced by current epic |
| `REV-EPIC-02` | AI receptionist review-only packet batch | Epic agent | strongest proof stack already exists | ready to queue |
| `REV-EPIC-03` | Meeting-to-action second-angle packet batch | Epic agent | cheapest pilot and natural attach offer | ready to queue |
| `REV-EPIC-04` | Inbox triage proof packaging | Epic agent | recurring-support lane needs proof parity | spec ready |
| `REV-EPIC-05` | Document packet generator packaging | Epic agent | attach lane needs better product surface | spec ready |
| `REV-TASK-01` | Lane refresh tasks | Local task runner | keep summaries and digests current | queued in pending |

## REV-EPIC-01: Workflow Cleanup Pilot Package

- Objective: turn the workflow cleanup lane into something that can be reviewed like a sellable fixed-scope service, not just discussed.
- Inputs:
  - `strategy/workflow-maps/jvt-lead-to-followup-flow.md`
  - `site/index.html`
  - `strategy/jvt-10k-by-mar-2027-plan.md`
- Deliverables:
  - workflow cleanup proof packet
  - workflow cleanup site demo page
  - workflow cleanup review-only outreach template
- Done when:
  - the lane has proof, packaging, price framing, and review boundary language
  - no external send or deployment is attempted

## REV-EPIC-02: AI Receptionist Review-Only Packet Batch

- Objective: convert the best intake candidates into review-only packets tied to one narrow paid-pilot ask each.
- Inputs:
  - `strategy/prospect-lists/ai-receptionist-intake-targets.csv`
  - `strategy/prospect-packet-prep/priority-review-queue-2026-06-11.md`
  - `outreach/templates/ai-receptionist-paid-pilot.md`
  - `site/ai-receptionist-intake-demo.html`
- Deliverables:
  - 3 to 5 review-only packet drafts
  - tightened subject/body variants
  - candidate-specific blockers list
- Done when:
  - every packet stays internal and review-only
  - each packet points to one workflow pain and one proof link

## REV-EPIC-03: Meeting-To-Action Second-Angle Packet Batch

- Objective: convert the meeting-to-action lane from proof-only into a prepared second-angle packet lane.
- Inputs:
  - `strategy/prospect-lists/meeting-to-action-targets.csv`
  - `site/meeting-to-action-demo.html`
  - `strategy/content-ops/meeting-to-action-content-packet-2026-06-11.md`
- Deliverables:
  - review-only packet drafts for the strongest candidates
  - one downloadable sample packet based on the demo
  - revised proof-path copy around lost action items after calls
- Done when:
  - the lane has a reusable packet sample and a draft batch ready for manual review

## REV-EPIC-04: Inbox Triage Proof Packaging

- Objective: close the gap between the internal case study and a public-safe or packet-safe proof surface.
- Inputs:
  - `strategy/case-studies/inbox-document-triage-case-study.md`
  - `runbooks/jvt-ops-runbook.md`
  - `site/index.html`
- Deliverables:
  - synthetic inbox sample
  - proof page or proof packet
  - fixed-scope copy for one shared-inbox pilot
- Done when:
  - the lane can be shown without exposing private mail
  - triage boundaries remain explicit

## REV-EPIC-05: Document Packet Generator Packaging

- Objective: package the existing packet examples into a cleaner product surface for accounting, legal, and adjacent admin workflows.
- Inputs:
  - `client-work/synthetic-examples/cpa-onboarding-packet.md`
  - `client-work/synthetic-examples/law-firm-intake-packet.md`
  - `strategy/revenue-opportunities.md`
- Deliverables:
  - combined review packet or proof sheet
  - clearer vertical boundary copy
  - site/demo placement plan
- Done when:
  - packet generation is easier to show as a productized attachment lane

## REV-TASK-01: Lane Refresh Tasks

- Objective: keep the execution surface current after packaging work lands.
- Queue owner: local task runner
- Task files:
  - `ops/agent-control/tasks/pending/2026-06-12-offer-segment-summary-refresh.json`
  - `ops/agent-control/tasks/pending/2026-06-12-priority-packet-review-queue-refresh.json`
  - `ops/agent-control/tasks/pending/2026-06-12-10k-execution-digest-refresh.json`
- Done when:
  - fresh summaries exist for manual review
  - the digest reflects the newer execution path
