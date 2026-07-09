#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
ENV_FILE="$ROOT/outreach/.env.local"
LOCK_DIR="$ROOT/outreach/schedules/auto-send.lock"
PYTHON_BIN="${JVT_PYTHON_BIN:-python3}"

mkdir -p "$ROOT/outreach/schedules/auto-send"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
  PYTHON_BIN="${JVT_PYTHON_BIN:-$PYTHON_BIN}"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "auto-send already running; exiting"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

"$PYTHON_BIN" "$ROOT/outreach/tools/auto_send_quality_pass.py" --send
