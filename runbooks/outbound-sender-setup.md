# Outbound Sender Setup

## Current Reality

- inbound mail is already routed through Cloudflare Email Routing
- Cloudflare Email Routing is not the outbound mailbox itself
- reviewed outbound sending needs a real SMTP or API-backed sender configuration

## Local Workflow

1. generate a draft packet into `outreach/queue/draft`
2. review it manually
3. move it into `outreach/queue/approved`
4. run a dry-run send check
5. only then run a real send

## Queue Helpers

Move a packet between queue states:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
python3 outreach/tools/move_packet.py \
  --stem 2026-04-09-the-siegel-law-firm-initial-introduction \
  --from draft \
  --to approved
```

Dry-run an approved packet:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
python3 outreach/tools/send_approved.py \
  --stem 2026-04-09-the-siegel-law-firm-initial-introduction
```

Real send after review:

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
python3 outreach/tools/send_approved.py \
  --stem 2026-04-09-the-siegel-law-firm-initial-introduction \
  --send
```

## Config

Use a local non-repo env file derived from:

- `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/outreach/.env.example`

The sender supports:

- `smtp`
- `resend`

Conservative controls:

- per-run cap: `JVT_SEND_MAX_PER_RUN`
- daily cap: `JVT_SEND_DAILY_LIMIT`
- delay between sends: `JVT_SEND_DELAY_SECONDS`

## Recommendation

- keep the first real send batch very small
- use dry-run first every time you change templates or sender settings
- send the first few emails only after reviewing the exact HTML/text packet
- keep replies human-reviewed even if local drafting is enabled
