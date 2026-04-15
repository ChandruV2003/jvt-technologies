# JVT Autonomy Operating Model

JVT should not run as an unbounded autonomous system. It should run as a bounded operator-assist system with explicit approval gates.

That means:

- the agent handles repetitive, low-risk work on its own
- the agent prepares decisions for higher-risk actions
- the operator stays available for commercial, financial, and reputation-sensitive choices

## The Right Model

### Autonomous by default

For:

- lead research
- CRM enrichment
- draft outreach generation
- inbox import and triage
- reply drafting
- smoke tests
- website refinement
- demo prep
- internal documentation

### Human-in-the-loop

For:

- real outbound send approval
- pricing changes
- payment setup
- bank and Stripe setup
- significant brand changes
- live infrastructure changes
- deleting important business records

## How The Operator Helps

The operator should not need to micromanage. The operator should only need to decide:

- yes
- no
- not yet
- revise this recommendation

That is why decision packets exist under:

- `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/pending`

Each packet should include:

- what the agent wants to do
- why it recommends that action
- what the risk level is
- what the alternatives are

## Current JVT Boundary

Today, JVT can already run most of the operational work:

- research leads
- build drafts
- triage inbound mail
- draft replies
- update and deploy the site
- run product smoke tests

JVT should still pause for:

- new send batches
- financial tool setup
- contract and pricing commitments
- materially different outreach strategy

## Recommended Near-Term Evolution

1. Keep reviewed send batches small.
2. Let the inbox agent continue receiving and drafting.
3. Use the decision queue for anything external-facing with commitment or risk.
4. Later, add recurring automation for:
   - daily inbox import
   - daily status snapshot
   - scheduled lead research tranches

## The Goal

The goal is not "the system never needs you."

The goal is:

- the system handles the busywork
- the system surfaces the actual decisions cleanly
- you spend your time making leverage decisions, not chasing state across files
