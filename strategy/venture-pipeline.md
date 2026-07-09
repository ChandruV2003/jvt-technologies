# JVT Venture Pipeline

Updated: 2026-06-10

This is the source-of-truth board for business-development ideas outside the
normal outreach queue. It keeps service revenue, vendor paths, franchises,
acquisitions, paper trading, and crypto/compute research from blending into one
unprioritized idea pile.

## Operating Rule

JVT productized services remain the primary cash-flow path for the March 2027
`$10k` target. Everything else is either a distribution channel, optionality, or
research until its economics and approval gates are clear.

## Active Priorities

1. JVT productized services: fastest and most aligned path.
2. Local partner/reseller channel: distribution leverage without new capital.
3. Vendor/subcontractor readiness: slower, but credible institutional path.
4. Low-overhead service franchise research: possible cash-flow business, but
   needs capital, diligence, and operator commitment.
5. Chick-fil-A operator path: monitored optionality, not a passive investment.
6. Small business acquisition search: research only until criteria are strict.
7. Paper AutoTrader R&D: paper-only learning and validation.
8. Crypto/compute/mining: read-only feasibility only.

## Approval Gates

- No spending, deposits, applications, or subscriptions without approval.
- No external contacts, prospect sends, partner outreach, or franchise inquiries
  without approval.
- No live trades, fund movement, wallets, mining, staking, or custody workflows.
- No legal, tax, financial, medical, or investment advice as autonomous output.

## Automation

The board is consumed by:

```bash
python3 ops/agent-control/venture_pipeline.py
python3 ops/agent-control/growth_ops_checkin.py
```

The report is written to:

- `ops/agent-control/state/latest-venture-pipeline.json`
- `ops/agent-control/state/latest-venture-pipeline.md`

