# Agent Control

This directory is the control layer for JVT's semi-autonomous operations.

The goal is not "do everything without restraint." The goal is:

- let the system handle low-risk recurring work on its own
- force a clean pause for higher-risk decisions
- give the operator a fast way to review and unblock the next step
- keep an audit trail of what the system decided and why

## Directory Layout

- `pending`: decision packets waiting on human input
- `approved`: decisions that were approved but not fully executed yet
- `rejected`: decisions that were explicitly declined
- `executed`: approved decisions that were carried out
- `decision-log.jsonl`: append-only history of approvals, rejections, and executions

## What The Agent Can Do Autonomously

- research and enrich leads
- generate draft outreach packets
- run smoke tests
- triage inbound mail
- draft responses for review
- refresh site content and deploy after internal validation
- prepare internal runbooks, pricing notes, and ops materials

## What Requires A Decision Packet

- sending a new outreach batch
- changing pricing or service terms materially
- changing domain, DNS, or email-provider setup
- opening or reconfiguring payment/banking tools
- deleting important data or replacing live infrastructure
- broadening outreach rules in a way that could affect deliverability or brand risk

## Operator Workflow

1. Review `status` output from the control scripts.
2. Open anything in `pending`.
3. If the recommendation makes sense, approve it.
4. If not, reject it or add a note with the adjustment.
5. Let the system execute only after approval.

Use the wrapper:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/reviewed_outreach.sh status
```

Create a decision packet:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/reviewed_outreach.sh request-decision outreach "Next reviewed batch" "Approve sending 5 reviewed national targets"
```

Approve or reject:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/reviewed_outreach.sh log-decision 2026-04-15-next-reviewed-batch approved "Proceed with five reviewed sends"
```
