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
5. `orchestrator.py` turns all queue, inbox, service, model, and venture state
   into ranked lanes and work items.
6. `eom_agent.py` picks the current executive focus and keeps the cash-flow
   work pointed at the $10k target.

The local task runner is not an arbitrary shell agent. It can only run known
handlers such as inbox triage briefs, outreach review briefs, follow-up review
briefs, proof-asset refreshes, pilot briefs, model-router status, Codex status,
paper-only trading refreshes, and venture digests.

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

## Current Human Gates

These still require operator approval before execution:

- dental voice prospect contact or live phone/provider setup,
- BITS/ballot prospect contact or real client data handling,
- pricing commitments,
- vendor/franchise applications,
- live trading/fund movement,
- wallets/mining/staking,
- social account connection or publishing.

