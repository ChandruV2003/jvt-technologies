#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/control-panel"
PYTHON_BIN="${JVT_CONTROL_PANEL_PYTHON:-/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend/.venv/bin/python}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8042}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python runtime not found: $PYTHON_BIN" >&2
  exit 1
fi

exec "$PYTHON_BIN" -m uvicorn app:app --app-dir "$APP_DIR" --host "$HOST" --port "$PORT" --reload
