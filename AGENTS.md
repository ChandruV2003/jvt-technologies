# JVT Technologies Agent Rules

## Machine and path model

- Primary runtime host: `m4-mac-mini`.
- Primary repo on the M4: `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies`.
- Local edit mirror on this Mac: `/Users/chandruv/Developer/.jvt-active-edit/JVT-Technologies`.
- If editing from the local mirror, sync changed files back to the M4 before validating live services.
- Do not say Wrangler is missing from the M4 unless `/opt/homebrew/bin/wrangler` is absent. The known state is that Wrangler exists on the M4.
- M4 wired LAN fallback from this MacBook:
  `ssh -i /Users/chandruv/.ssh/m4_mac_mini_ed25519 -o IdentitiesOnly=yes c.s.d.v.r.s.@192.168.1.9`.
  Use this when the Tailscale SSH alias is unhealthy.
- If M4 loopback checks fail with `can't assign requested address`, `curl`
  cannot reach `127.0.0.1` listeners, or
  `ops/agent-control/state/latest-m4-tcp-pressure.json` shows tens of thousands
  of `TIME_WAIT` sockets, treat the M4 network stack as critical. App-level JVT
  restarts are not enough. Root/sudo TCP tuning, Tailscale network-extension
  reset, or a controlled M4 reboot is the recovery path.

## Control panel and ops checks

- Control panel local M4 URL: `http://127.0.0.1:8042`.
- Control panel Tailscale URL: `https://m4-mac-mini.tailee4a3f.ts.net/`.
- Fresh check-in command:

```bash
ssh m4-mac-mini 'cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies && python3 ops/agent-control/growth_ops_checkin.py'
```

- Venture/cash-flow pipeline command:

```bash
ssh m4-mac-mini 'cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies && python3 ops/agent-control/venture_pipeline.py'
```

- Venture pipeline source of truth:
  `strategy/venture-pipeline.json`
- Latest venture report:
  `ops/agent-control/state/latest-venture-pipeline.md`

- Status API:

```bash
ssh m4-mac-mini 'python3 - <<'"'"'PY'"'"'
import json, urllib.request
print(json.dumps(json.load(urllib.request.urlopen("http://127.0.0.1:8042/api/status", timeout=30)), indent=2)[:4000])
PY'
```

- Core launch agents include `com.jvt.control-panel`, `com.jvt.watchdog`, `com.jvt.orchestrator`, `com.jvt.growth-ops-checkin`, `com.jvt.agent-interop-check`, `com.jvt.mailbox-listener`, `com.jvt.lead-research`, and `com.jvt.daily-wave-prep`.

## Website deployment

- Public site source: `site/`.
- Deploy from the M4, not from the local mirror, unless Wrangler is deliberately installed locally.
- M4 deploy command:

```bash
ssh m4-mac-mini 'cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/site && ./deploy.sh'
```

- Wrangler binary on the M4 is expected at `/opt/homebrew/bin/wrangler`.
- Current known deployment blocker: Cloudflare Pages API returns auth error `10000` for project `jvt-technologies-site`.
- If deployment fails with auth error `10000`, the problem is Cloudflare auth/token/account access, not missing website files and not missing Wrangler on the M4.
- The local Mac currently may not have `wrangler` in PATH. That only means local deployment from this shell is unavailable.
- Raw non-interactive SSH calls to `/opt/homebrew/bin/wrangler` may fail with `env: node: No such file or directory` unless `/opt/homebrew/bin` is in PATH. The `site/deploy.sh` script already exports that PATH.

## Outreach guardrails

- Do not send prospect emails unless the user explicitly authorizes sending.
- Before sending approved packets, run:

```bash
ssh m4-mac-mini 'cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies && python3 outreach/tools/quality_gate_approved.py'
```

- Hold generic page-title company names, placeholder contacts, suspicious scraped emails, mismatched domains, recruiting addresses, BPO/outsourcing targets, and off-target categories.
- No-reply follow-ups must be treated separately from initial outreach and still require review/approval before sending.

## Financial, crypto, and trading guardrails

- Keep trading work paper-only unless the user gives explicit authorization for live trading.
- Do not move funds, place live trades, create wallets, stake, mine, change brokerage settings, or create custody workflows without explicit approval.
- Treat crypto mining as research-only unless a separate hardware/power/custody plan is approved.
- Market monitoring may collect data, score watchlists, run paper simulations, and produce decision packets. It must not autonomously buy or sell.

## Strategic operating principle

- JVT should not look like a generic "AI everything" company.
- Public hook: "We fix messy intake, inbox, meeting, and document workflows."
- Prioritize sellable, narrow service lines: AI receptionist/intake, meeting-to-action packets, inbox/document triage, workflow cleanup, private document assistant, and managed AI operations.
- Keep franchise, acquisition, AutoTrader, crypto, compute, and hardware ideas in the venture pipeline as separate lanes. They can be researched and scored autonomously, but anything involving money, applications, live trading, wallets, mining, staking, vendor registration, or external commitments requires explicit approval.

## Debian supervisor layer

- Reliable autonomous operations now run from Debian, not macOS LaunchAgents alone.
- Supervisor path on Debian: `/home/sysadmin/developer-workspaces/active/jvt-ops-supervisor`.
- Cron cadence on Debian: every 15 minutes via `run_jvt_ops_supervisor.sh`.
- Latest supervisor reports:
  - `/home/sysadmin/developer-workspaces/active/jvt-ops-supervisor/state/latest-supervisor.json`
  - `/home/sysadmin/developer-workspaces/active/jvt-ops-supervisor/state/latest-supervisor.md`
- Debian reaches the M4 through SSH host alias `jvt-m4` using `~/.ssh/jvt_ops_ed25519`.
- Debian JVT backups should use SSH host alias `jvt-m4-lan`, not Tailscale,
  when the wired LAN path is available. `jvt-m4-lan` maps to `192.168.1.9` and
  uses the same restricted `~/.ssh/jvt_ops_ed25519` key from Debian
  `192.168.1.10`.
- Debian backup script:
  `/home/sysadmin/JVT-Ops/scripts/backup_m4_jvt.sh`. It defaults to
  `JVT_M4_BACKUP_HOST=jvt-m4-lan` and can still be overridden with
  `JVT_M4_BACKUP_SOURCE`.
- If M4 `launchctl` shows no `com.jvt.*` jobs, do not assume JVT is idle until checking the Debian supervisor report. On June 16, 2026, macOS `gui/501` launchd was unavailable over SSH and `user/501` bootstrap returned error 5, so Debian cron became the source of truth.
- The supervisor may run watchdog, orchestrator, growth check-in, lead research, follow-up prep, strict follow-up auto-approval, quality-gated auto-send, and service keepalives. It does not bypass spend/trade/wallet/external-commitment guardrails.
- Credit-heavy epic-agent work is skipped unless explicitly invoked with `--allow-credit-heavy`.
