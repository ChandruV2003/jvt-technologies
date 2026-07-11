#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
BASE_URL="http://${JVT_MLX_BIND_HOST:-127.0.0.1}:${JVT_MLX_PORT:-11435}"

if curl -fsS --max-time 5 "$BASE_URL/health" >/dev/null 2>&1; then
  echo "JVT MLX idle proxy is healthy at $BASE_URL"
  exit 0
fi

exec "$ROOT/ops/agent-control/install_m4_mlx_model_server_launch_agent.sh"
