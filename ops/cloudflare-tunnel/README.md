# JVT Cloudflare Voice Tunnel

Purpose: expose the local M4 Mac Mini voice intake app at `http://127.0.0.1:8066` through a public Cloudflare hostname for phone-provider webhooks.

## Current Status

- Tunnel name: `jvt-voice-intake`
- Tunnel ID: `6027a4cc-c688-4fcf-a247-b10acd25f544`
- Public hostname: `https://voice.jvt-technologies.com`
- Local voice app: `http://127.0.0.1:8066`
- Runtime: user LaunchAgent `com.jvt.voice-cloudflare-tunnel`
- Cloudflared config: `/Users/c.s.d.v.r.s./.cloudflared/config.yml`
- Cloudflared credentials: `/Users/c.s.d.v.r.s./.cloudflared/6027a4cc-c688-4fcf-a247-b10acd25f544.json`
- Logs: `ops/cloudflare-tunnel/logs/`

Verified on 2026-05-24:

```bash
curl https://voice.jvt-technologies.com/health
curl -X POST https://voice.jvt-technologies.com/twilio/inbound \
  -d 'From=%2B15555550123&To=%2B15555550999&CallSid=CA_public_check'
```

The voice agent is still intentionally in dry-run mode. Live voice intake still requires `OPENAI_API_KEY`, a phone provider/Twilio number, and an explicit switch from `JVT_VOICE_DRY_RUN=1` to live mode.

## Useful Commands

Check tunnel LaunchAgent:

```bash
launchctl print gui/$(id -u)/com.jvt.voice-cloudflare-tunnel
```

Restart tunnel:

```bash
launchctl kickstart -k gui/$(id -u)/com.jvt.voice-cloudflare-tunnel
```

Check tunnel details:

```bash
/opt/homebrew/bin/cloudflared tunnel info jvt-voice-intake
```

Check voice agent:

```bash
launchctl print gui/$(id -u)/com.jvt.inbound-voice-agent
curl http://127.0.0.1:8066/health
```
