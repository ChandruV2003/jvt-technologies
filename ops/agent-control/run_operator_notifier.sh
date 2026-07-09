#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
LOCK_DIR="$ROOT/ops/agent-control/state/operator-notifier.lock"
PYTHON_BIN="${JVT_PYTHON_BIN:-python3}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "operator notifier already running; exiting"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

"$PYTHON_BIN" "$ROOT/ops/agent-control/operator_notifier.py" --notify
