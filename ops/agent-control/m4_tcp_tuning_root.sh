#!/bin/zsh
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "m4_tcp_tuning_root.sh must run as root/admin." >&2
  exit 1
fi

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
STATE_DIR="$ROOT/ops/agent-control/state"
mkdir -p "$STATE_DIR"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BEFORE="$STATE_DIR/m4-tcp-tuning-before-$TS.txt"
AFTER="$STATE_DIR/latest-m4-tcp-tuning.txt"
JSON="$STATE_DIR/latest-m4-tcp-tuning.json"

{
  echo "checked_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  sysctl net.inet.tcp.msl net.inet.ip.portrange.first net.inet.ip.portrange.last
  netstat -m | sed -n '1,20p'
} > "$BEFORE"

# These are runtime sysctl values. They are intentionally conservative:
# - Lower TIME_WAIT retention from 15s to 5s so dead client sockets drain faster.
# - Expand the ephemeral port range to reduce port exhaustion from local agents.
sysctl -w net.inet.tcp.msl=5000
sysctl -w net.inet.ip.portrange.first=10000
sysctl -w net.inet.ip.portrange.last=65535

{
  echo "checked_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  sysctl net.inet.tcp.msl net.inet.ip.portrange.first net.inet.ip.portrange.last
  netstat -m | sed -n '1,20p'
} > "$AFTER"

/usr/bin/python3 - "$BEFORE" "$AFTER" "$JSON" <<'PY'
import json
import sys
from pathlib import Path

before = Path(sys.argv[1])
after = Path(sys.argv[2])
out = Path(sys.argv[3])

def parse(path):
    values = {"path": str(path)}
    for line in path.read_text().splitlines():
        if line.startswith("checked_at="):
            values["checked_at"] = line.split("=", 1)[1]
        elif line.startswith("net."):
            key, value = line.split(": ", 1)
            values[key] = value
    return values

out.write_text(json.dumps({"before": parse(before), "after": parse(after)}, indent=2, sort_keys=True) + "\n")
PY

echo "TCP tuning applied. Before: $BEFORE"
cat "$AFTER"
