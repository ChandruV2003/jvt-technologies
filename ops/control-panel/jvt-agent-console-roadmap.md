# JVT Agent Console Roadmap

## Goal

The control panel should become the operator console for the JVT agent system running on the Mac mini.

It should give one place to:

- see what the business is doing
- see which agent is doing what
- approve, reject, or revise pending actions
- inspect client, lead, inbox, and delivery state
- intervene quickly without micromanaging the whole system

## Operator Experience

The operator should be able to answer four questions quickly:

1. What is happening now?
2. What needs my approval?
3. What is blocked?
4. What should happen next?

## Target Views

### 1. Overview

Show:

- leads by status
- outreach queue counts
- inbox counts
- pending decision count
- active client count
- active project count
- last run status for each agent

### 2. Agents

One card per agent:

- orchestrator
- lead research
- outreach
- intake
- solution planning
- delivery
- QA and review
- client operations
- billing and admin

Each card should show:

- current status
- last action
- last run time
- next scheduled run
- current task or idle reason
- pause and run-now controls

### 3. Decision Queue

Show all decision packets with:

- category
- risk level
- recommendation
- alternatives
- current state
- operator note history

### 4. Leads And Outreach

Show:

- recent high-fit leads
- draft, review, approved, and sent queues
- recommended next batch
- follow-up candidates

### 5. Intake And Projects

Show:

- new inquiry packets
- discovery notes
- transcript-derived requirement summaries
- scoped planning packets
- active delivery tasks

### 6. Clients And Deliverables

Show:

- client registry
- active engagements
- service line
- last activity
- next milestone
- deliverable status

### 7. Model Console

Keep:

- fast local model
- stronger local review model
- explicit use for drafting, summarizing, and checking

Do not position this as the business itself.
It is a tool pane inside the operating console.

## Orchestrator Behavior

The orchestrator should not act like a magic autonomous brain.

It should behave like a traffic controller:

- read system state
- pick the next specialized agent
- collect outputs
- open a decision packet when a risk boundary is reached
- publish a recommended next action

## Existing Data Sources

The control panel can already draw from:

- `lead-pipeline/data/jvt_leads.sqlite3`
- `outreach/queue/*`
- `outreach/inbox/*`
- `ops/agent-control/*`
- `~/Documents/JVT-Technologies/00-admin/client-registry.csv`

That means the panel already has enough underlying state to become a real operator console.

## Versioned Build Plan

### V1

Deliver:

- overview page improvements
- explicit agent list
- agent status from simple JSON status files
- decision queue prominence
- client registry pane

### V2

Deliver:

- pause and run-now controls
- intake packet creation from transcripts and notes
- project and delivery tracking
- exception view for failed jobs and stale queues

### V3

Deliver:

- orchestrator recommendations in the UI
- linked client, lead, and project timelines
- richer audit trail
- per-agent metrics and reliability snapshots

## Operating Rule

The control panel is not supposed to hide the system from you.

It is supposed to compress the system into a reviewable form so that:

- agents handle the repetitive work
- the Mac mini remains the canonical operations box
- the operator can step in at the right time with minimal friction
