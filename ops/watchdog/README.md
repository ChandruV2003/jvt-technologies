# JVT Watchdog

Consolidated local health/readiness check for JVT operations.

It checks:

- public site and Other Offerings section
- control panel API
- inbound voice health
- launch agents for core services
- mailbox listener freshness
- lead research freshness
- outreach queue counts
- approved-packet QC
- service-line execution board
- paper-trader research snapshot presence

It does not:

- send outreach
- spend money
- place trades
- call external prospects
- change payment/banking/provider setup

## Run Once

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
ops/watchdog/run_watchdog.sh
```

Outputs:

- `ops/watchdog/state/latest-watchdog.json`
- `ops/watchdog/state/latest-watchdog.md`

## Install Launch Agent

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
ops/watchdog/install_launch_agent.sh
```

Runs every 15 minutes.
