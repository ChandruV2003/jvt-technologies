# JVT Decision Matrix

This matrix defines where autonomy stops and operator approval starts.

## Autonomous

The agent may do these without waiting:

- lead research and enrichment
- website smoke tests
- demo smoke tests
- outbound draft generation
- inbound mail import and triage
- draft reply generation
- internal documentation updates
- local run and deploy validation

## Approval Required

The agent should create a decision packet first for:

- any new batch of real external outreach
- any change to pricing floors or payment terms
- any change to the public offer position that materially changes scope
- any banking, invoicing, payout, or tax-related account action
- any mailbox, domain, or DNS change on live infrastructure
- any deletion of important business records
- any meaningful increase in send volume or cadence

## Hard Stops

The system should not do these on its own:

- mass-send cold email at bulk scale
- move money
- accept legal terms blindly
- buy products or subscriptions without approval
- send invoices to real clients without a reviewed engagement path
- expose private services publicly without an explicit decision

## Recommended Early Limits

- outreach batch size: 3 to 5 per reviewed batch
- daily outbound limit: 5
- keep review-first workflow for every real send
- prefer operator approval for anything client-facing that introduces commitment, pricing, or legal language
