#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
APP_ROOT="$ROOT/products/Private-AI-Lab/apps/jvt-inbound-voice-agent"
DEFAULT_PYTHON="$ROOT/products/Private-AI-Lab/apps/private-doc-intel-demo/backend/.venv/bin/python"
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON}"
cd "$APP_ROOT"

if [[ -f ".env.local" ]]; then
  set -a
  source ".env.local"
  set +a
fi

export JVT_LOCAL_AUDIO_BRIDGE_READY="${JVT_LOCAL_AUDIO_BRIDGE_READY:-0}"
exec "$PYTHON_BIN" -m uvicorn tools.local_audio_bridge_stub:app --host 127.0.0.1 --port "${JVT_LOCAL_AUDIO_BRIDGE_PORT:-8761}"
