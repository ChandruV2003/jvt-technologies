# JVT Control Panel

This is the local operator console for JVT Technologies.

It is meant to run on the Mac mini and give one place to:

- inspect lead, inbox, queue, and decision status
- review pending decision packets
- move decisions through approval states
- inspect recent outreach and inbox activity
- talk directly to the local MLX model running on this Mac

## Start It

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/control-panel/run_control_panel.sh
```

Default URL:

- `http://127.0.0.1:8042`

Remote tailnet access:

- once Tailscale Serve is enabled on the tailnet, publish it with:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/control-panel/publish_to_tailscale.sh
```

## Current Runtime Assumption

The panel uses the existing product backend virtualenv for FastAPI and MLX dependencies:

- `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend/.venv/bin/python`

That keeps this first version light and avoids introducing another Python environment immediately.

## What It Can Do

- show status snapshot
- list recent leads
- list recent draft and sent outreach packets
- show pending, approved, rejected, and executed decisions
- create a new decision packet
- transition a decision through approval states
- send prompts to the local fast or strong MLX model

## What It Does Not Yet Do

- start and stop background agents from the UI
- send outreach directly from the UI
- stream tokens from the local model
- authenticate remote users

This is an internal local control panel, not a public-facing web app.

## LaunchAgent

Install and start it as a persistent local service:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/control-panel/install_launch_agent.sh
```
