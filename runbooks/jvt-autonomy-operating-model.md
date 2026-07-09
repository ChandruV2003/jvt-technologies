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
4. Keep the venture/cash-flow pipeline separate from the outreach queue so new
   business ideas are scored before they consume attention or capital.
5. Later, add recurring automation for:
   - daily inbox import
   - daily status snapshot
   - scheduled lead research tranches

## Venture Pipeline

The venture pipeline is the default place for cash-flow ideas that are not plain
JVT outreach tickets.

Source of truth:

- `strategy/venture-pipeline.json`

Generated reports:

- `ops/agent-control/state/latest-venture-pipeline.json`
- `ops/agent-control/state/latest-venture-pipeline.md`

Refresh command:

```bash
python3 ops/agent-control/venture_pipeline.py
```

The pipeline may autonomously research, score, draft, compare, and prepare
internal validation artifacts for:

- JVT productized services
- partner and reseller channels
- vendor/subcontractor readiness
- low-overhead franchise research
- Chick-fil-A/operator optionality
- small business acquisitions
- paper-only AutoTrader research
- crypto, compute, and mining feasibility

It must stop for approval before:

- spending money
- submitting applications
- contacting third parties
- sending prospect emails
- making vendor registrations
- moving funds or trading live
- creating wallets, mining, staking, or custody workflows

## Executive Operations Manager

The EOM agent is the single "what should happen next" layer.

Manifest:

- `ops/agent-control/agents/executive-ops-manager.json`

Generated brief:

- `ops/agent-control/state/latest-eom-brief.json`
- `ops/agent-control/state/latest-eom-brief.md`

Refresh command:

```bash
python3 ops/agent-control/eom_agent.py
```

The EOM reads orchestrator, venture pipeline, growth check-in, watchdog, and
interop state. It selects the highest-priority stage-only action, separates
approval-gated work from autonomous prep, and keeps the operator from needing to
reconstruct the business state manually.

## Local Task Runner

The local task runner is the bounded executor for safe internal work.

Manifest:

- `ops/agent-control/agents/local-task-runner.json`

Queue:

- `ops/agent-control/tasks/pending`
- `ops/agent-control/tasks/running`
- `ops/agent-control/tasks/completed`
- `ops/agent-control/tasks/held`
- `ops/agent-control/tasks/failed`

Generated status:

- `ops/agent-control/state/latest-local-task-runner.json`
- `ops/agent-control/state/latest-local-task-runner.md`

Install/run:

```bash
python3 ops/agent-control/local_task_runner.py
ops/agent-control/install_local_task_runner_launch_agent.sh
```

Daily task seeding:

- `ops/agent-control/growth_ops_checkin.py` seeds the standard internal task
  set once per day.
- Seeded tasks include state refresh, content backlog, venture scout index,
  offer-segment summary, $10k execution digest, and paper-only trader refresh.
- The seeder checks pending, running, completed, held, and failed task folders
  before writing a task, so it should not duplicate the same day's work.

Supported task types are allowlisted in code. The runner must not accept
arbitrary shell commands from task JSON. Anything involving sends, spending,
account changes, live trades, wallets, mining, staking, public posting,
applications, registrations, or deletion must be held for operator approval.

## The Goal

The goal is not "the system never needs you."

The goal is:

- the system handles the busywork
- the system surfaces the actual decisions cleanly
- you spend your time making leverage decisions, not chasing state across files

## Debian Supervisor Layer

As of June 16, 2026, Debian is the always-on manager for JVT operations.
The M4 Mac mini remains the worker and demo host, but macOS LaunchAgents are not
trusted as the only scheduler because the GUI launchd domain may be unavailable
over SSH.

Supervisor path on Debian:

```bash
/home/sysadmin/developer-workspaces/active/jvt-ops-supervisor
```

Cron cadence:

```bash
*/15 * * * * /home/sysadmin/developer-workspaces/active/jvt-ops-supervisor/run_jvt_ops_supervisor.sh
```

Manual run:

```bash
ssh macmini-i7-debian 'cd /home/sysadmin/developer-workspaces/active/jvt-ops-supervisor && ./run_jvt_ops_supervisor.sh --force'
```

Latest accountability report:

```bash
ssh macmini-i7-debian 'sed -n "1,220p" /home/sysadmin/developer-workspaces/active/jvt-ops-supervisor/state/latest-supervisor.md'
```

The supervisor runs safe internal work and quality-gated outreach work. It starts
or checks local M4 services, refreshes watchdog/orchestrator/growth state,
prepares follow-ups, strictly auto-approves only clean follow-up packets, and runs
the auto-send quality gate. It does not spend money, trade live, create wallets,
mine, stake, submit applications, register vendors, post to social accounts, or
make external commitments.

Credit-heavy Codex/epic-agent work is disabled by default and requires an
explicit `--allow-credit-heavy` run.

