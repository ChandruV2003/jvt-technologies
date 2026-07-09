# M4 TCP Management

JVT local health checks can fail even when services are listening if the M4 host
has exhausted ephemeral ports or network mbufs. The observed symptoms are:

- local connects to `127.0.0.1` fail with `EADDRNOTAVAIL`
- `netstat -anv -p tcp` shows very high `TIME_WAIT`, `SYN_SENT`, or closing sockets
- `netstat -m` shows high network memory use or denied mbuf requests

## Runtime tuning

Use `ops/agent-control/m4_tcp_tuning_root.sh` from the M4. It requires
administrator privileges because macOS restricts `sysctl -w`.

The script records before/after state under `ops/agent-control/state`, then
applies conservative runtime values:

- `net.inet.tcp.msl=5000`
- `net.inet.ip.portrange.first=10000`
- `net.inet.ip.portrange.last=65535`

These values do not disable services. They shorten socket cleanup and expand the
ephemeral port pool available to local agents.

## Watchdog

`ops/agent-control/m4_tcp_pressure_watchdog.py` runs without sudo and records:

- TCP state counts
- loopback health for model/control-panel/voice/demo ports
- mbuf pressure
- LaunchAgent status for JVT model plus known high-churn local services
- top per-process socket pressure

Install it with:

```zsh
ops/agent-control/install_m4_tcp_pressure_watchdog_launch_agent.sh
```

Latest state files:

- `ops/agent-control/state/latest-m4-tcp-pressure.json`
- `ops/agent-control/state/latest-m4-tcp-pressure.md`
- `ops/agent-control/logs/m4-tcp-pressure.jsonl`

## Recovery order

1. Run the watchdog and confirm whether loopback health is failing.
2. Apply root TCP tuning.
3. Wait at least 60 seconds and rerun the watchdog.
4. If mbufs remain denied or loopback connects still fail, do a controlled
   reboot. A reboot is the clean recovery for already-exhausted kernel network
   memory.
