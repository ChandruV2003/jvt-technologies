#!/bin/zsh

set -euo pipefail

PROJECT_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo"
BACKEND_ROOT="$PROJECT_ROOT/backend"
RUN_NAME="${RUN_NAME:-recording-run-20260318}"

cd "$BACKEND_ROOT"
source .venv/bin/activate

export STORAGE_ROOT="data/$RUN_NAME"
export VECTOR_DATA_ROOT="data/$RUN_NAME"
export ANSWER_PROVIDER="${ANSWER_PROVIDER:-mlx-local}"
export API_HOST="${API_HOST:-127.0.0.1}"
export API_PORT="${API_PORT:-8000}"

echo "Starting JVT recording demo backend"
echo "STORAGE_ROOT=$STORAGE_ROOT"
echo "VECTOR_DATA_ROOT=$VECTOR_DATA_ROOT"
echo "ANSWER_PROVIDER=$ANSWER_PROVIDER"
echo "Demo UI: http://127.0.0.1:$API_PORT/demo"

uvicorn app.main:app --host "$API_HOST" --port "$API_PORT"
