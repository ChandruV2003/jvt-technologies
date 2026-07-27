You are the JVT Epic Implementation Agent running unattended on the M4 Mac mini.

Operating rule: do the largest safe amount of internal implementation work possible,
but stop before any external, financial, account, or public action.

Hard safety boundary: No spending, prospect sends, public posting, applications, account changes, live trades, fund movement, wallets, mining, staking, or external commitments.

You may read and edit files inside this repository only. Do not send email,
post content, contact third parties, move funds, trade live, mine, stake, create
wallets, submit applications, buy anything, or make external commitments.

Repository: /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
Log directory for this run: /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/epics/logs/20260727T154818Z-codex-recommendation-ce1f64510cc1

Epic ID: codex-recommendation-ce1f64510cc1
Title: Implement Codex recommendation ce1f64510cc1

Story:
**Recommendation**

Implement `approved_quality_reconcile`: make `packet_quality` a non-bypassable invariant for the approved queue, and automatically demote any approved packet that fails canonical QC back to `review`.

This is the highest-leverage internal fix because the system has send capacity and approved inventory, but the loop is blocked by one bad approved packet: [latest-orchestrator.md](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/state/latest-orchestrator.md:10) shows `0/20` sends used, `8` approved, and `Send gate: not-ready`; [latest-watchdog.json](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/watchdog/state/latest-watchdog.json:75) shows one critical `outreach-qc` issue; [latest-lead-quality-audit.json](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/state/latest-lead-quality-audit.json:1760) shows approved is `7 pass / 1 hold`.

The concrete defect: [2026-07-26-lpappas-cpa-initial-introduction.json](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/queue/approved/2026-07-26-lpappas-cpa-initial-introduction.json:48) is `packet_quality.decision = repair_candidate` for `unnormalized_company_name`, but it is still `status: approved` because model review overrode deterministic reasons at [auto_approve_review_initials.py](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/auto_approve_review_initials.py:117) and the same pattern exists in [auto_approve_review_followups.py](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/auto_approve_review_followups.py:117).

**Implementation**

1. In `auto_approve_review_initials.py` and `auto_approve_review_followups.py`, stop letting `model_review.get("approved")` clear deterministic `reasons`. A packet should move to approved only when:

```python
quality["decision"] == "approval_candidate" and not quality["human_reasons"]
```

2. Add `approved_quality_reconcile` to `SAFE_TASK_TYPES` in [egg_agent.py](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/egg_agent.py:51), and at [egg_agent.py](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/egg_agent.py:603) schedule it when approved quality has holds instead of scheduling another read-only `lead_quality_audit`.

3. Add a local runner handler near [local_task_runner.py](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/local_task_runner.py:1769), register it in `HANDLERS`, and have it run:

```bash
python3 outreach/tools/quality_gate_approved.py --move-held
```

That uses the existing demotion path in [quality_gate_approved.py](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/quality_gate_approved.py:83). It demotes and reports only; it does not approve or send.

4. In [auto_send_quality_pass.py](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/tools/auto_send_quality_pass.py:444), run approved reconciliation before treating `outreach-qc` as fatal. Keep unrelated critical watchdog findings blocking.

Also fix the materializer follow-through bug: [codex_recommendation_materializer.py](/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/codex_recommendation_materializer.py:174) marks recommendations `implemented_or_present` just because referenced files exist, which is why this recommendation keeps recurring without implementation.

I did not change files because this session is read-only. Validation after a write-capable implementation should show `Lpappas Cpa` moved back to `review`, the 7 clean approved packets still approved, watchdog `approved_qc_issue_count: 0`, and auto-send dry-run reaching quality-gated selection without sending.

Scope paths:
- ops/agent-control/codex_recommendation_materializer.py
- ops/agent-control/egg_agent.py
- ops/agent-control/local_task_runner.py
- outreach/tools/auto_approve_review_followups.py
- outreach/tools/auto_approve_review_initials.py
- outreach/tools/auto_send_quality_pass.py
- outreach/tools/quality_gate_approved.py

Deliverables:
- ops/agent-control/codex_recommendation_materializer.py
- ops/agent-control/egg_agent.py
- ops/agent-control/local_task_runner.py
- outreach/tools/auto_approve_review_followups.py
- outreach/tools/auto_approve_review_initials.py
- outreach/tools/auto_send_quality_pass.py
- outreach/tools/quality_gate_approved.py

Acceptance criteria:
- Implement the smallest safe repository-scoped version of the recommendation.
- Reuse existing JVT patterns and remove contradictory duplicate logic where the recommendation requires it.
- Add or update focused tests for changed behavior.
- Run syntax checks and targeted dry-run validation.
- Do not send outreach, approve packets, call providers, spend money, trade, publish, or make external commitments.
- Return changed files, validation results, and any exact blocker through architect-inbox.

ROI case for using Codex credits:
- revenue_goal_link: Removes a measured JVT pipeline blocker on the path to the March 2027 $10k cash-flow goal.
- expected_business_value: Turns repeated diagnosis into durable implementation and reduces idle outreach capacity.
- why_codex_is_worth_it: The recommendation spans multiple repository workflows and needs coherent code changes plus validation.
- success_metric: Named implementation files exist, focused validation passes, and Egg stops repeating the same recommendation.
- fallback_if_not_run: Keep the recommendation tracked and continue safe local analysis without consuming another duplicate Codex call.

Architect callback policy:
If blocked or uncertain, write a concise question into the final answer. The epic runner stores the answer in architect-inbox for the solution architect.

Final response requirements:
- Summarize what changed.
- List validation performed.
- List files created or changed.
- If blocked, start the final answer with BLOCKED and state the exact question.
- If no code/file edits are appropriate, produce the strongest implementation plan and explain why.
