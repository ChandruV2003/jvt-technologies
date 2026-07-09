# JVT Epic Agent Operating Model

The epic agent is for large story-style work that should continue on the M4 Mac
mini without asking the solution architect to do every low-level step.

## Core Idea

Small recurring tasks stay in `ops/agent-control/tasks`.

Large durable stories go in `ops/agent-control/epics`.

The epic agent wakes on the M4, takes one queued epic at a time, runs bounded
Codex CLI execution, writes logs, and creates an architect handoff. If the Mac
is offline, the queue just waits on disk.

Default operating posture:

- Local deterministic agents handle small recurring work.
- Local model agents should be used for drafting/review where practical.
- Codex CLI is reserved for large queued epics that justify credit spend.
- Queued Codex epics defer automatically when the daily/cooldown budget is hit.

## Directories

- `ops/agent-control/epics/queued`
- `ops/agent-control/epics/running`
- `ops/agent-control/epics/done`
- `ops/agent-control/epics/blocked`
- `ops/agent-control/epics/held`
- `ops/agent-control/epics/logs`
- `ops/agent-control/epics/architect-inbox`

## Execution Modes

- `architect_brief`: write an architect handoff only.
- `codex_readonly_plan`: run Codex CLI in read-only mode and capture a plan.
- `codex_workspace_write`: run Codex CLI with repo workspace-write access.

No mode may spend money, send prospect email, post publicly, submit
applications, modify financial accounts, trade live, move funds, create wallets,
mine, stake, or make external commitments.

## Credit And Stagger Policy

Policy file:

`ops/agent-control/policies/epic-agent-policy.json`

Current defaults:

- `max_codex_epics_per_day`: `1`
- `min_seconds_between_codex_epics`: `21600`
- `require_roi_case_for_codex_epics`: `true`
- `prefer_local_for_small_tasks`: `true`

When the policy blocks a Codex run, the epic remains in
`ops/agent-control/epics/queued` and the latest status records it as
`deferred`. This is intentional; deferment is not a failure.

Local-first rule:

- Use `ops/agent-control/tasks` for deterministic status refreshes, content
  packet generation, paper-only trading refreshes, prospect summaries, proof
  packet generation, and other repeatable low-level work.
- Use `architect_brief` for no-credit planning handoffs.
- Use `codex_readonly_plan` or `codex_workspace_write` only for large stories
  that are worth the credit cost.

Codex ROI requirement:

Every `codex_readonly_plan` or `codex_workspace_write` epic must include a
`roi_case` object. If it is missing required fields, the runner leaves the epic
queued and records it as `deferred`.

Required ROI fields:

- `revenue_goal_link`
- `expected_business_value`
- `why_codex_is_worth_it`
- `success_metric`
- `fallback_if_not_run`

## LaunchAgent

Install:

```bash
ops/agent-control/install_epic_agent_runner_launch_agent.sh
```

Manual run:

```bash
python3 ops/agent-control/epic_agent_runner.py --max-epics 1
```

Status:

- `ops/agent-control/state/latest-epic-agent.json`
- `ops/agent-control/state/latest-epic-agent.md`
- `ops/agent-control/state/epic-agent.out.log`
- `ops/agent-control/state/epic-agent.err.log`

## Architect Callback

The agent cannot directly speak into every live desktop thread. Instead it
writes callback material into:

`ops/agent-control/epics/architect-inbox`

The solution architect reads that inbox, answers blockers, and queues follow-up
epics when needed.

## Epic Spec Minimum Fields

```json
{
  "id": "2026-06-12-example",
  "title": "Example Epic",
  "execution_mode": "codex_workspace_write",
  "codex_enabled": true,
  "requires_approval": false,
  "story": "Large story brief...",
  "scope_paths": ["strategy/", "runbooks/"],
  "deliverables": ["What the agent should create or update"],
  "acceptance_criteria": ["How the agent knows the story is done"],
  "roi_case": {
    "revenue_goal_link": "$10,000 gross cash collected by 2027-03-31",
    "expected_business_value": "What revenue, conversion, delivery, or risk-reduction result this should create.",
    "why_codex_is_worth_it": "Why this should consume Codex instead of local deterministic/model agents.",
    "success_metric": "Concrete evidence that the run moved the business forward.",
    "fallback_if_not_run": "What local agents or manual review can do while it waits."
  },
  "timeout_seconds": 1800
}
```
