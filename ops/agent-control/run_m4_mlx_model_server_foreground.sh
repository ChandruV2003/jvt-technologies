#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
STATE_DIR="$ROOT/ops/agent-control/state"
LOG_DIR="$ROOT/ops/agent-control/logs"
HOST="${JVT_MLX_BIND_HOST:-127.0.0.1}"
PORT="${JVT_MLX_PORT:-11435}"
UPSTREAM_HOST="${JVT_MLX_UPSTREAM_HOST:-127.0.0.1}"
UPSTREAM_PORT="${JVT_MLX_UPSTREAM_PORT:-11438}"
MODEL="${JVT_MLX_MODEL_PATH:-/Users/c.s.d.v.r.s./.cache/huggingface/hub/models--mlx-community--Qwen3-8B-4bit/snapshots/545dc4251c05440727734bcd94334791f6ab0192}"
MODEL_ID="${JVT_MLX_MODEL:-mlx-community/Qwen3-8B-4bit}"

mkdir -p "$STATE_DIR" "$LOG_DIR"

exec /usr/bin/python3 "$ROOT/ops/agent-control/mlx_idle_proxy.py" \
  --service-name "jvt-m4-mlx-idle-proxy" \
  --listen-host "$HOST" \
  --listen-port "$PORT" \
  --upstream-host "$UPSTREAM_HOST" \
  --upstream-port "$UPSTREAM_PORT" \
  --model-path "$MODEL" \
  --model-id "$MODEL_ID" \
  --state-path "$STATE_DIR/latest-m4-mlx-model-server.json" \
  --pid-path "$STATE_DIR/m4-mlx-model-server.pid" \
  --model-log-path "$LOG_DIR/mlx-server-$UPSTREAM_PORT-idle.log" \
  --max-tokens "${JVT_MLX_MAX_TOKENS:-220}" \
  --temp "${JVT_MLX_TEMP:-0.0}" \
  --timeout "${JVT_MLX_TIMEOUT_SECONDS:-180}" \
  --cold-start-timeout "${JVT_MLX_COLD_START_TIMEOUT_SECONDS:-120}" \
  --idle-seconds "${JVT_MLX_IDLE_SECONDS:-600}" \
  --idle-check-seconds "${JVT_MLX_IDLE_CHECK_SECONDS:-15}" \
  --queue-capacity "${JVT_MLX_QUEUE_CAPACITY:-8}"
