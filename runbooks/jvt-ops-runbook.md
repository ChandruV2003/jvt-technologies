# JVT Ops Runbook

## Current operating loop

1. Run the Growth Ops check-in on the M4.
2. Read `/api/status`, `/api/growth-ops/checkin`, and `/api/orchestrator/status`.
3. Triage inbox first.
4. Review follow-ups separately from first-touch outreach.
5. Run the approved quality gate before any send.
6. Send only packets that pass both automated and manual recipient-quality checks.
7. Refresh the orchestrator after changes.

## Known command snippets

Fresh check-in:

```bash
ssh m4-mac-mini 'cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies && python3 ops/agent-control/growth_ops_checkin.py'
```

Launch agent snapshot:

```bash
ssh m4-mac-mini 'launchctl list | egrep "com.jvt.(control-panel|watchdog|orchestrator|growth-ops-checkin|agent-interop-check|mailbox-listener|lead-research|daily-wave-prep)"'
```

Website deploy:

```bash
ssh m4-mac-mini 'cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/site && ./deploy.sh'
```

If website deploy fails with Cloudflare API auth error `10000`, fix Cloudflare auth/token/account access. Do not misdiagnose it as a missing Wrangler issue on the M4.

## Current unresolved infrastructure issue

- Cloudflare Pages deploy from the M4 has recently failed with:
  - endpoint: `/accounts/42ef726325168e016d5133cdd8638f00/pages/projects/jvt-technologies-site`
  - error: `Authentication error [code: 10000]`
- M4 Wrangler exists:
  - `/opt/homebrew/bin/wrangler`
- Local shell may not have Wrangler, but local Wrangler is not required if deploying from the M4.
- If raw SSH calls to `/opt/homebrew/bin/wrangler` fail with `env: node: No such file or directory`, prepend `/opt/homebrew/bin` to PATH or use `site/deploy.sh`; this is PATH hygiene, not a missing Wrangler install.
- Preferred non-interactive fix is `site/.env.local` with `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`; see `site/.env.local.example`.

## Market research lane

Purpose: evaluate public companies and AI-adjacent market opportunities through repeatable paper-only analysis.

Allowed:

- watchlist creation
- news/event collection
- earnings/calendar tracking
- sentiment and catalyst notes
- paper portfolio simulations
- risk scoring
- daily decision packets

Not allowed without explicit approval:

- live trades
- options orders
- day-trading execution
- fund movement
- margin changes
- brokerage setting changes
- crypto wallets, staking, mining, custody, or exchange actions

## Business focus

The company should be positioned as a practical workflow cleanup company, not a vague AI lab.

Use this hook:

> We fix messy intake, inbox, meeting, and document workflows.

Push these service lines first:

- AI receptionist / intake
- meeting-to-action packets
- inbox and document triage
- workflow automation cleanup
- private document assistant
- managed AI operations
