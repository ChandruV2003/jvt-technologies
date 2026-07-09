# JVT Agent Operating Blueprint

## Purpose

This document defines how JVT should operate internally on the Mac mini.

The goal is not a pile of unrelated agents.

The goal is a bounded operator-assist system where:

- JVT sells private AI workflow solutions to clients
- JVT uses internal agents to reduce busywork and keep execution moving
- the operator stays in control of commercial, financial, delivery, and reputation-sensitive decisions

## Core Principle

Externally, JVT should look like a focused private AI systems and workflow automation company.

Internally, JVT should run as a small agent operating system with clear roles.

Clients buy outcomes.
Agents are how JVT delivers those outcomes efficiently.

## Agent Roles

### 1. Orchestrator Agent

The orchestrator is the top-level coordinator.

It should:

- inspect the global business state
- decide which specialized agent should act next
- gather outputs into decision packets for the operator
- pause automatically when a human approval gate is reached
- push status into the control panel

It should not:

- send risky outbound communications without approval
- change pricing, banking, or contracts on its own
- delete important records without approval

### 2. Lead Research Agent

Responsible for:

- finding new target firms
- enriching lead records
- scoring fit by vertical and offer match
- rejecting weak or generic targets

Primary outputs:

- lead DB updates
- dated research CSV tranches
- fit notes and target recommendations

### 3. Outreach Agent

Responsible for:

- drafting first-touch emails
- drafting follow-ups
- moving packets between draft, review, approved, and sent states
- tracking reply status and next-action recommendations

Primary outputs:

- outreach packets
- send recommendations
- follow-up queues

### 4. Intake Agent

Responsible for:

- turning calls, transcripts, notes, and client emails into structured requirements
- identifying business goals, constraints, privacy requirements, and success criteria
- creating clean intake packets for delivery planning

Primary outputs:

- intake summaries
- requirement checklists
- implementation assumptions

### 5. Solution Planning Agent

Responsible for:

- turning intake material into proposed scopes
- mapping the right offer shape
- outlining deployment options
- proposing milestones, risks, and review checkpoints

Primary outputs:

- scoped plan
- recommended architecture
- risk notes
- draft statement-of-work inputs

### 6. Delivery Agent

Responsible for:

- preparing product and workflow changes
- configuring client-specific document and workflow setups
- preparing demo or pilot environments
- assembling deployment artifacts

Primary outputs:

- configured pilot assets
- implementation runbooks
- deployment notes

### 7. QA And Review Agent

Responsible for:

- checking groundedness and source traceability
- checking formatting and delivery completeness
- checking that outputs match agreed scope
- escalating anything risky, weak, or ambiguous

Primary outputs:

- review notes
- acceptance checklists
- revision recommendations

### 8. Client Operations Agent

Responsible for:

- maintaining client registry state
- creating workspace folders
- keeping status snapshots current
- tracking deliverables, handoffs, and follow-ups

Primary outputs:

- client registry updates
- workspace initialization
- status notes

### 9. Billing And Admin Agent

Responsible for:

- preparing invoice drafts
- tracking admin tasks
- surfacing payment follow-up needs
- organizing confirmations and supporting records

Primary outputs:

- invoice drafts
- billing reminders
- admin packets

## Approval Gates

### Autonomous By Default

Allowed without approval:

- lead research
- lead enrichment
- outreach drafting
- inbox import and triage
- reply drafting
- intake summary preparation
- internal planning drafts
- runbook generation
- QA checks
- status reporting

### Human Approval Required

Must pause for operator approval:

- sending real outreach
- sending client-facing replies that matter commercially
- changing pricing or packaging
- signing off on scope and delivery commitments
- changing payment setup
- changing live infrastructure in material ways
- deleting important records
- changing brand, positioning, or risk posture materially

### Human-Owned

Should stay primarily human:

- discovery calls
- final pricing decisions
- contract signature decisions
- final delivery signoff
- conflict handling
- relationship management when sensitive

## Standard Delivery Flow

1. Lead Research Agent finds and scores a prospect.
2. Outreach Agent prepares a reviewed packet.
3. Operator approves or rejects send.
4. Inbox and Intake Agents organize replies, transcripts, and notes.
5. Solution Planning Agent proposes scope and implementation shape.
6. Operator approves scope direction.
7. Delivery Agent prepares the pilot or workflow implementation.
8. QA Agent checks the output.
9. Operator signs off on delivery.
10. Client Operations Agent tracks the engagement and next steps.

## Mac Mini System Design

The Mac mini should be the canonical JVT operations box.

It should own:

- lead research
- queue management
- inbox triage
- intake packets
- decision packets
- control-panel state
- client registry
- local model-assisted drafting

The current system already has parts of this in place:

- lead DB
- outreach queues
- inbox import
- decision packet folders
- control panel
- local models
- client workspace scaffolding

The missing piece is a clearer orchestrator layer and cleaner UI visibility over all active agents.

## Control Panel Target

The control panel should evolve into an operator console with:

- global status snapshot
- per-agent status and last action
- pending approval queue
- lead and outreach queue views
- intake and project view
- client registry view
- model console for local assistance
- audit trail for what the system did

## Near-Term Build Order

1. Add an explicit agent registry and status file for each active agent.
2. Expose agent status in the control panel.
3. Add pause, resume, and run-now controls per agent.
4. Add intake packet ingestion from transcripts and notes.
5. Add project and client-stage visibility alongside lead visibility.
6. Add orchestrator logic that creates decision packets instead of improvising risky actions.

## Guardrails

- Agents should optimize for traceability, not just output volume.
- Every external-facing action should be reviewable after the fact.
- Every major decision should leave an audit trail.
- Human override must always be simple.
- JVT should scale through disciplined operating roles, not through uncontrolled autonomy.
