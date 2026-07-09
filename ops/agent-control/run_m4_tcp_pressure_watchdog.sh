#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
cd "$ROOT"

set +e
/usr/bin/python3 "$ROOT/ops/agent-control/m4_tcp_pressure_watchdog.py" "$@"
STATUS=$?
set -e

if [[ "$STATUS" != "0" ]]; then
  echo "m4_tcp_pressure_watchdog.py returned $STATUS; severity is recorded in state/latest-m4-tcp-pressure.*"
fi

exit 0
