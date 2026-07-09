#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/jvt-inbound-voice-agent"
DEFAULT_PYTHON="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend/.venv/bin/python"
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON}"

cd "$APP_ROOT"

if [[ -f ".env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env.local"
  set +a
fi

PORT="${JVT_VOICE_PORT:-8066}"

exec "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
