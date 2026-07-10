# JVT Agent Assignment And Rate-Limit Model

Generated: 2026-07-06

This is the operating map for how JVT work is assigned between scripts, local
models, the MacBook large model, and Codex CLI.

## Control Loop

1. `growth_ops_checkin.py` runs every 30 minutes.
2. It refreshes health, watchdog, venture pipeline, orchestrator, and EOM state.
3. It seeds daily tasks plus six-hour workfeed tasks from the live orchestrator
   state.
4. `local_task_runner.py` runs every 15 minutes and executes only allowlisted
   internal tasks.
5. The local runner classifies every task with
   `ops/agent-control/policies/agent-assignment-policy.json`, then performs a
   deterministic self-review before it can mark the task completed.
6. `orchestrator.py` turns all queue, inbox, service, model, and venture state
   into ranked lanes and work items.
7. `eom_agent.py` picks the current executive focus and keeps the cash-flow
   work pointed at the $10k target.

The local task runner is not an arbitrary shell agent. It can only run known
handlers such as inbox triage briefs, outreach review briefs, follow-up review
briefs, proof-asset refreshes, pilot briefs, model-router status, Codex status,
paper-only trading refreshes, and venture digests.

## Work Hierarchy

Use the system like epics, features, stories, and tasks:

- Epic: largest durable repo-changing work. Owned by `epic_agent_runner.py`.
  Codex CLI can be used here only when the epic has an ROI case and passes the
  capped `epic-agent-policy.json` gates.
- Feature: multi-step business/product capability. Owned by the AI director and
  orchestrator. Should use the MacBook large local model when the power gate
  allows it, otherwise the M4 model.
- Story: one concrete capability improvement. Owned by `local_task_runner.py`
  through allowlisted handlers. It must leave artifacts and pass self-review.
- Task: small status check, QA brief, packet prep, or health refresh. Owned by
  deterministic scripts or lightweight M4 model routing.

The intent is that quick fixes do not wait for Chandru. The local runner should
execute, cross-check the result, and either mark it completed, fail it with
evidence, or leave a larger item for the epic agent.

## Model Assignment

- M4 Mac mini `m4-mlx`: always-on local model endpoint at
  `http://127.0.0.1:11435`, model `mlx-community/Qwen3-8B-4bit`.
- M4 Mac mini secondary MLX endpoint: health-checked at
  `http://127.0.0.1:11436`; used by local services that need a second local
  model worker.
- M4 router: `http://127.0.0.1:8760`.
- MacBook large model: `http://100.90.245.45:8770`, model `qwen2.5:14b`,
  gated by `http://100.90.245.45:8769/health`.

Router policy:

- `triage`, `lead_scoring`, `outreach_copy`, and `status_summary` use the M4
  MLX backend.
- `strategy`, `deep_research`, `product_spec`, and `code_planning` use the
  MacBook large model when the MacBook is online, on AC power, at least 80%
  battery, and on the 140W charger.
- If the MacBook gate blocks, work falls back to the M4 backend.

## Codex CLI Escalation

Codex CLI is for expensive reasoning/code-planning escalations only. It should
not be used for ordinary queue bookkeeping, status snapshots, or deterministic
script work.

Current policy:

- Default model: `gpt-5.5`.
- Default reasoning: `medium`.
- Default sandbox: `read-only`.
- Daily execute cap: `8`.
- Daily `gpt-5.5` cap: `5`.
- Daily high/xhigh cap: `2`.
- Execution requires `--execute`; status/dry-run is allowed without spending.
- Prompts containing external-action phrases such as prospect sending, live
  trades, funds movement, wallets, mining, staking, applications, or payment
  setup are blocked.

Codex CLI may be used for:

- hard product specs,
- code planning,
- difficult copy or strategy review,
- debugging the agent system itself,
- summarizing high-stakes internal decisions.

Codex CLI should not be used for:

- routine outreach send decisions,
- live account actions,
- social publishing,
- live phone-call activation,
- payment/banking changes,
- live trades or crypto operations.

Codex CLI is not called by `local_task_runner.py`. If a local task discovers it
is actually epic-sized, it should fail or produce an epic spec for the epic
agent instead of using Codex directly.

## Self-Review Rule

Every local runner task now records:

- assignment level,
- feature lane,
- model tier,
- self-review policy,
- self-review findings.

The deterministic self-review checks handler success, subprocess steps,
artifact existence, explicit guardrails, and approval-gated language. Strict
tasks fail when required artifacts are missing. This is the cross-check layer
that should catch obvious “running but not ready” or “note created but no test
run” gaps without needing Chandru to point them out.

## Outreach Rule

A real inbox hit does not block unrelated outreach. It only blocks follow-ups to
the same active contact/domain until the human-response path is handled.

Allowed outbound path:

1. Packet starts in `outreach/queue/review`.
2. Auto/manual QA verifies recipient, domain/company fit, copy tone, and service
   fit.
3. Packet moves to `approved`.
4. `quality_gate_approved.py` checks approved packets.
5. `auto_send_quality_pass.py --send` selects safe packets within caps.
6. `send_approved.py` sends and archives the packet to `sent`.

Manual verification override:

- Allowed only when a public source URL confirms the recipient is a real
  business contact for the target.
- Does not bypass invalid email, recruiting/careers contact, internal recipient,
  suspicious local part, or off-target-category checks.

Current outbound caps:

- Initial cap: `10/day`.
- Follow-up cap: `10/day`.
- Base total cap: `20/day`.
- Dynamic max total cap: `30/day` only when inbox, watchdog, and TCP health are
  green.
- Per-run auto-send cap: `5`.

## Mythos Executive Generator

`mythos_agent.py` is the goal-aware executive work generator. It reads the
current company state, JVT design ethos, queue counts, watchdog health, voice
readiness, lead research, opportunity state, model-router state, proof assets,
and stale-state signals, then creates only allowlisted internal tasks under
`ops/agent-control/tasks/pending`.

Mythos is not an external-action agent. It does not send, approve, spend, trade,
publish, enable providers, create wallets, submit applications, or make
commitments. It creates executable internal work for the local task runner or
leaves larger unclear work for the capped epic path.

Execution paths:

- `com.jvt.mythos-agent` runs Mythos every 15 minutes.
- `growth_ops_checkin.py` also runs Mythos before invoking the local runner.
- `ai_director.py` can seed `mythos_task_generator` when Mythos has not produced
  state yet.

This gives JVT a loop that continuously asks: what is stale, what is blocked,
what can advance safely, and what next internal task gets the company closer to
the March 2027 cash-flow goal?

## Current Human Gates

These still require operator approval before execution:

- dental voice prospect contact or live phone/provider setup,
- BITS/ballot prospect contact or real client data handling,
- pricing commitments,
- vendor/franchise applications,
- live trading/fund movement,
- wallets/mining/staking,
- social account connection or publishing.
