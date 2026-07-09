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
- auto-approve clean packets that pass recipient/company/domain quality checks
- send approved quality-pass packets within the outbound caps when inbox and watchdog gates are clean
- run validation checks
- triage inbound mail
- draft responses for review
- refresh site content and deploy after internal validation
- prepare internal runbooks, pricing notes, and ops materials

## What Requires A Decision Packet

- raising outbound caps or bypassing the quality gate
- sending held, suspicious, mismatched, or manually flagged packets
- changing pricing or service terms materially
- changing domain, DNS, or email-provider setup
- opening or reconfiguring payment/banking tools
- deleting important data or replacing live infrastructure
- broadening outreach rules in a way that could affect deliverability or brand risk

## Standing Outbound Delegation

As of 2026-06-13, the operator delegated repeat approval for quality-pass outreach. The machine may approve and send only packets that pass the outbound policy and quality gate, only within daily caps, and only when inbox/watchdog gates are clean. Bad addresses, placeholder contacts, mismatched domains, generic page-title company names, recruiting contacts, and suspicious scraped names must stay held for review.

The M4 currently does not have `rg` installed. Use `grep`/`find` in launch-agent scripts unless ripgrep is explicitly installed later.

Key commands:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/run_auto_send_quality_pass.sh
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/quality_gate_approved.py --move-held
```

Reports are written under:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/schedules/auto-send
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/quality-reports
```

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
# JVT Agent Control

## Model and Company-Memory Control Plane

The current control plane has three internal-only primitives for keeping the
company agent stack coordinated:

- `model_router.py`: local OpenAI-compatible router on `127.0.0.1:8760`.
  It routes routine work to the M4 MLX server and registers the MacBook worker
  behind the existing power gate.
- `codex_escalation_runner.py`: guarded Codex CLI wrapper. It reports
  readiness/caps by default and only executes Codex when `--execute` is passed.
- `jvt_ops_db.py`: durable company-memory sync into
  `ops/agent-control/data/jvt_ops.sqlite3` for leads, services, service fit,
  interactions, queue snapshots, and model backend status.

These scripts do not send prospect emails, spend money, trade, create wallets,
mine, stake, or make external commitments.
