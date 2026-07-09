# Pilot Brief: IT / Ballot Services Agentic Workflow System

Generated: 2026-07-01T19:33:25+00:00

Status: internal planning brief. Do not contact the prospect, request credentials, process real ballots, or make service commitments from this file.

## Target Customer

An IT consulting / AV operations company that supports housing-complex board meetings and provides third-party ballot/election-process services.

## Pain / Demand

- Meeting logistics create repeated admin work before, during, and after board meetings.
- Ballot/election support likely involves deadlines, checklists, eligibility files, notices, forms, status tracking, and audit-sensitive documentation.
- Staff need fewer manual reminders, cleaner packets, and safer review workflows without replacing human control over election-sensitive decisions.

## Proposed Offer

A review-first agentic operations layer for repeatable meeting and ballot-service workflows.

Initial paid pilot scope:

1. Intake agent: converts incoming client requests into structured job packets.
2. Meeting-prep agent: builds agenda/checklist/task packets for AV and board-meeting logistics.
3. Ballot-process checklist agent: tracks milestone checklists, required documents, deadlines, missing items, and staff-review status.
4. Document-generation agent: drafts notices, instruction sheets, status emails, meeting summaries, and internal task lists from approved templates.
5. Audit-log agent: records what was generated, who reviewed it, what changed, and what was sent.

## Hard Boundaries

- Do not process live ballots in an autonomous black box.
- Do not determine eligibility, winners, vote validity, quorum, or legal compliance.
- Do not send election-related notices or results without human approval.
- Do not store unnecessary PII; use least-privilege access and explicit retention rules.
- Treat every output as draft/review-required until the prospect defines their compliance process.

## Agent Workflow Sketch

```text
Request received
  -> Intake classifier
  -> Job packet
  -> Missing-info checklist
  -> Human review
  -> Template/document draft
  -> Human approval
  -> Audit log + status board update
```

## Pricing Hypothesis

- Discovery/workflow map: $500-$1,500 fixed fee.
- Narrow pilot build: $2,500-$7,500 depending on integrations and templates.
- Managed AI operations retainer: $500-$2,000/month for monitoring, prompt/template updates, QA, and workflow changes.

## Delivery Complexity

Medium-high. The admin automation is straightforward, but ballot/election-adjacent workflows are sensitive and require strict human review, audit trails, permission controls, and careful language.

## Major Risks

- Legal/compliance ambiguity around housing-complex election processes.
- PII and voter/owner eligibility data handling.
- Prospect may use custom spreadsheets, PDFs, email inboxes, or legacy tools with messy data.
- Any hallucinated deadline/result/instruction could create serious trust issues.
- Scope can sprawl into a full election-management platform if not constrained.

## Next Validation Step

Run a 45-minute workflow-discovery call using synthetic examples only. Capture:

- top three repeated workflows
- documents/templates they already use
- systems of record
- what humans must approve
- what data is sensitive
- current turnaround time and bottlenecks
- one pilot workflow that can be tested without live election data

## First Demo To Build

Use a synthetic board-meeting/election-support request and generate:

- intake summary
- required-info checklist
- staff task board
- draft client status email
- audit log entry

This should be presented as operational workflow automation, not as an autonomous election decision system.
