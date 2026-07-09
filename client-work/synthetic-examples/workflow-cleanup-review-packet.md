# Synthetic Workflow Cleanup Review Packet

Updated: 2026-06-12

Status: synthetic internal proof. Review-only. Do not present as a live client deployment.

## Scenario

Summit Advisory Group has one painful admin workflow:

- a lead form comes in
- discovery-call notes live in email and notebooks
- document requests are typed from scratch
- follow-ups depend on memory
- AI drafts are used ad hoc, but nobody trusts them

The owner wants one fixed-scope cleanup before paying for a broader system.

## Current Workflow Snapshot

1. Website form sends an email to the office manager.
2. The office manager copies the contact into a spreadsheet.
3. Discovery-call notes are added later by hand.
4. Missing-document requests are drafted from scratch.
5. Follow-up timing depends on whoever remembers.
6. No-response leads disappear without a clean state or queue.

## Friction Found

- the same intake facts get retyped multiple times
- there is no single owner once the first email is answered
- missing documents are not tracked in one checklist
- AI drafts exist, but there is no review rule or standard template
- no-response follow-ups are inconsistent

## Proposed Future State

- one intake queue for new requests
- one reviewed summary packet after every form or call
- one missing-information checklist
- one follow-up draft template
- one visible status model: `new`, `needs-docs`, `scheduled`, `in-review`, `follow-up`, `closed`
- one weekly no-response queue for manual review

## Fixed-Scope JVT Pilot

Pilot shape: one workflow, one team, one review boundary

Target price: `$1,500` fixed scope

Target timeline: `10 business days`

### 10-Day Plan

- Days 1-2: map the current workflow and list repeated handoffs
- Days 3-4: define allowed statuses, owners, and review checkpoints
- Days 5-7: build the intake packet, missing-doc checklist, and follow-up draft
- Days 8-9: test the flow on synthetic or internal sample requests
- Day 10: tune rules, handoff notes, and operating checklist

## Example Reviewed Output

### Intake Summary

Prospect requested bookkeeping cleanup and monthly advisory support after a discovery call. The owner wants a proposal this week, but the team is missing bank statements, payroll access details, and the current bookkeeping close date.

### Missing-Information Checklist

- latest bank statements
- bookkeeping platform access details
- payroll provider and last payroll date
- current month close status
- preferred proposal deadline

### Internal Routing

- office manager: send the missing-doc checklist
- delivery lead: review scope fit and note likely cleanup size
- owner: confirm whether proposal or paid diagnostic is the next step
- follow-up queue: reopen in three business days if the documents have not arrived

### Draft Follow-Up For Review

Hi [Client Name],

Thanks again for the call. Before we scope the cleanup accurately, please send the latest bank statements, bookkeeping access details, payroll-provider information, and the current month close status. Once those arrive, we can confirm the right next step and timeline.

Best,
[Team]

## Success Scorecard

- every new request has an owner
- first response happens from one template instead of scratch
- missing documents are tracked in one checklist
- no-response items appear in a visible review queue
- ad hoc AI drafts become a reviewed workflow step instead of an invisible side habit

## Review Boundary

- no unreviewed client messaging
- no automated pricing promises
- no legal, tax, financial, or compliance advice
- staff remain responsible for external communication and scope decisions

## Sales Use

Use this as a review-only proof asset for the workflow cleanup lane. The promise is not "full automation." The promise is one messy workflow turned into a tighter operating system with review checkpoints.
