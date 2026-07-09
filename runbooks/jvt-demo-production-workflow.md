# JVT Demo Production Workflow

This runbook keeps demo creation repeatable for JVT Technologies LLC without turning every new demo into a one-off build.

## Demo Tiers

### Tier 1: Fast Screen Demo

Use for early prospect outreach.

- One narrow workflow.
- Synthetic or public sample documents only.
- Two-minute screen recording or hosted local demo.
- Human review before sending.

### Tier 2: Prospect-Specific Demo

Use after a prospect replies or shares requirements.

- Uses the prospect's industry and workflow language.
- Uses synthetic documents modeled after the prospect's public context.
- Includes a short before-and-after story: current manual search, private AI answer, cited source.
- No client confidential data unless an agreement is in place.

### Tier 3: Implementation Pilot

Use only after scope and payment terms are clear.

- Uses actual client documents in a controlled workspace.
- Has a documented ingestion path, access rules, and deletion/export process.
- Includes acceptance criteria and a handoff checklist.

## First Demo Ideas

- Private document intelligence for law firms: search policies, templates, and matter notes with cited answers.
- Intake triage assistant: summarize inbound requests, extract missing fields, and draft the next email.
- Operations knowledge assistant: turn SOPs, PDFs, and shared-folder documents into an internal Q&A tool.
- Proposal/document generator: convert notes and source docs into a first-pass proposal, checklist, or client memo.
- Voice-narrated demo video: generate a short walkthrough from slide images and an approved local voice workflow.

## Voice Policy

Use local voice generation for internal drafts only unless the model license allows commercial use. Do not upload Chandru's voice recordings or any client voice/audio to cloud services without explicit approval.

## Standard Demo Packet

Each demo should produce:

- `README.md`: what the demo proves and how to run it.
- `sample_docs/`: synthetic documents used by the demo.
- `script.md`: the human-readable walkthrough.
- `recording/`: exported screen recording or narrated video.
- `review_notes.md`: manual review notes, known limitations, and whether it is safe to send.

## Approval Gate

Before a demo is sent externally, confirm:

- The documents are synthetic, public, or explicitly approved.
- The workflow claims match what the demo actually does.
- The video/email does not imply a client relationship that does not exist.
- The model and voice tooling are legally usable for the intended audience.
