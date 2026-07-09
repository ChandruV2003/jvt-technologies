#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
STATE_DIR="$ROOT/ops/agent-control/state"
LOG_DIR="$ROOT/ops/agent-control/logs"
HOST="${JVT_MLX_BIND_HOST:-127.0.0.1}"
PORT="${JVT_MLX_PORT:-11435}"
MODEL="${JVT_MLX_MODEL_PATH:-/Users/c.s.d.v.r.s./.cache/huggingface/hub/models--mlx-community--Qwen3-8B-4bit/snapshots/545dc4251c05440727734bcd94334791f6ab0192}"
MODEL_ID="${JVT_MLX_MODEL:-mlx-community/Qwen3-8B-4bit}"
BASE_URL="http://$HOST:$PORT"

mkdir -p "$STATE_DIR" "$LOG_DIR"

write_status() {
  local state="$1"
  local message="$2"
  python3 - "$STATE_DIR/latest-m4-mlx-model-server.json" "$state" "$message" "$BASE_URL" "$MODEL" "$MODEL_ID" <<'PY'
import json
import sys
from datetime import datetime, timezone

path, status, message, base_url, model_path, model_id = sys.argv[1:7]
payload = {
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "status": status,
    "message": message,
    "base_url": base_url,
    "model_path": model_path,
    "model_id": model_id,
}
open(path, "w", encoding="utf-8").write(json.dumps(payload, indent=2) + "\n")
PY
}

if [[ ! -d "$MODEL" ]]; then
  write_status "error" "MLX model directory is missing: $MODEL"
  exit 1
fi

if curl -fsS --max-time 5 "$BASE_URL/health" >/dev/null 2>&1; then
  write_status "ok" "M4 MLX model server is already healthy."
  exit 0
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  write_status "error" "Port $PORT is listening but health check failed."
  exit 1
fi

nohup python3 -m mlx_lm server \
  --model "$MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  --max-tokens "${JVT_MLX_MAX_TOKENS:-220}" \
  --temp "${JVT_MLX_TEMP:-0.0}" \
  --chat-template-args '{"enable_thinking":false}' \
  >> "$LOG_DIR/mlx-server-$PORT.log" 2>&1 &

echo $! > "$STATE_DIR/m4-mlx-model-server.pid"
sleep 8

if curl -fsS --max-time 10 "$BASE_URL/health" >/dev/null 2>&1; then
  write_status "ok" "M4 MLX model server started successfully."
  exit 0
fi

write_status "error" "M4 MLX model server did not respond after start."
exit 1
