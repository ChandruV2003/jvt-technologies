#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
cd "$ROOT"

export JVT_MODEL_ROUTER_TIMEOUT_SECONDS="${JVT_MODEL_ROUTER_TIMEOUT_SECONDS:-90}"

/usr/bin/python3 "$ROOT/ops/agent-control/mythos_agent.py" --max-new-tasks 6 --max-pending 12
