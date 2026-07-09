#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
cd "$ROOT"

/usr/bin/python3 "$ROOT/ops/agent-control/orchestrator.py"
