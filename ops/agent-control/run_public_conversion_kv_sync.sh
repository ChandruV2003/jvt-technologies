#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$ROOT"

/usr/bin/python3 "$ROOT/ops/agent-control/public_conversion_kv_sync.py" --max-records 100
