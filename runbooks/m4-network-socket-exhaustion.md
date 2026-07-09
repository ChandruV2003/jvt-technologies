# M4 Network Socket Exhaustion Runbook

Last updated: 2026-06-21

## Summary

The M4 Mac mini can have JVT services listening on their expected ports while
local health checks still fail with:

```text
OSError [Errno 49] Can't assign requested address
curl: (7) Failed to connect to 127.0.0.1 ... Couldn't connect to server
```

This is not necessarily an application crash. On 2026-06-21 the machine had:

- more than 41,000 TCP sockets in `TIME_WAIT`
- more than 500 sockets in `SYN_SENT`
- network memory near exhaustion, with mbuf allocation failures
- JVT ports listening, but new loopback connections failing

## Impact

When this happens, the JVT watchdog marks public site, control panel, and voice
intake as critical even if the services are still present. Auto-send correctly
blocks while those critical findings are active.

## Useful Checks

```bash
python3 /tmp/jvt_tcp_counts.py
netstat -m | head -80
for port in 11435 8042 8066 8000; do
  lsof -nP -iTCP:$port -sTCP:LISTEN
  python3 - <<PY
import socket
port=$port
s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(("127.0.0.1", port))
    print("connect ok", port)
except Exception as e:
    print("connect fail", port, type(e).__name__, e)
finally:
    s.close()
PY
done
```

## 2026-06-21 Findings

High-churn or relevant non-JVT services:

- `org.ntc.whisper-large-server`
  - command: `whisper_large_server.py --host 0.0.0.0 --port 8766`
- `com.daynadante.homeagent.bridge`
  - command: `HomeAgent/run_bridge_agent.py`
  - port: `7788`
- `org.ntc.translation-tts-server`
  - command: `m4_translation_tts_server.py --host 100.66.210.59 --port 8767`
- Dante Controller had a stuck local `SYN_SENT` to port `8028`, but was not the
  main socket-volume source.

Non-disruptive restart attempts were made with:

```bash
launchctl kickstart -k gui/$(id -u)/org.ntc.whisper-large-server
launchctl kickstart -k gui/$(id -u)/com.daynadante.homeagent.bridge
launchctl kickstart -k gui/$(id -u)/org.ntc.translation-tts-server
```

Stale Whisper and translation PIDs required `TERM`, then relaunch through
launchd. HomeAgent restarted normally. This did not clear the kernel socket
pressure.

## Constraints

Do not disable the NTC/HomeAgent/Dante services unless explicitly asked. The
preferred policy is to keep them running where possible and use restarts rather
than permanent shutdown.

The user-level account could not change TCP sysctls because `sudo` required a
password:

```text
sudo: a password is required
```

Potential root-only mitigations:

- lower `net.inet.tcp.msl`
- expand `net.inet.ip.portrange.first`
- controlled reboot

## Recommended Recovery

If socket counts stay high and loopback connects continue failing after service
restarts, schedule a controlled M4 reboot. A reboot is the cleanest way to clear
kernel socket/mbuf exhaustion while preserving LaunchAgent-managed services.

After reboot:

1. Confirm the M4 is reachable over Tailscale/SSH.
2. Confirm LaunchAgents are loaded.
3. Confirm local ports connect.
4. Run JVT watchdog.
5. Run auto-send only after watchdog is clean and caps/quality gates pass.

## JVT Guardrail

Do not bypass the watchdog block just because listeners exist. If local connect
checks fail with `Errno 49`, the host is not healthy enough for autonomous
outbound sends.
