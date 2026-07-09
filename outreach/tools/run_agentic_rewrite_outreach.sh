#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
ENV_FILE="$ROOT/outreach/.env.local"
LOCK_DIR="$ROOT/outreach/schedules/copywriter.lock"
PYTHON_BIN="python3"

mkdir -p "$ROOT/outreach/schedules/copywriter"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

if [ -n "${JVT_PYTHON_BIN:-}" ] && [ -x "$JVT_PYTHON_BIN" ]; then
  PYTHON_BIN="$JVT_PYTHON_BIN"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "agentic copywriter already running; exiting"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

ARGS=(
  "$ROOT/outreach/tools/agentic_rewrite_outreach.py"
  --root "$ROOT"
  --queue review
  --queue approved
  --limit "${JVT_COPYWRITER_REWRITE_LIMIT:-3}"
  --write
  --exit-zero-on-held
)

if [ "${JVT_COPYWRITER_INCLUDE_INITIAL:-0}" = "1" ]; then
  ARGS+=(--include-initial)
fi

if [ "${JVT_COPYWRITER_REWRITE_EXISTING:-0}" = "1" ]; then
  ARGS+=(--rewrite-existing)
fi

"$PYTHON_BIN" "${ARGS[@]}"
