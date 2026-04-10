#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/Private-AI-Lab"
PROJECT_ROOT="$ROOT/apps/private-doc-intel-demo"
BACKEND_ROOT="$PROJECT_ROOT/backend"
JVT_ROOT="$ROOT/JVT-Technologies"
SCRIPT_ROOT="$JVT_ROOT/demo-packaging/scripts"
CAPTURE_ROOT="$JVT_ROOT/demo-packaging/captures"
STAMP="$(date +%Y%m%d-%H%M%S)"
RUN_NAME="recording-run-$STAMP"
OUTPUT_PATH="${1:-$CAPTURE_ROOT/jvt-private-document-assistant-$STAMP-silent.mp4}"
PLAYWRIGHT_VIDEO_DIR="$CAPTURE_ROOT/playwright-videos-$STAMP"
PID_FILE="$CAPTURE_ROOT/.recording-backend-$STAMP.pid"
PLAYWRIGHT_PID_FILE="$CAPTURE_ROOT/.recording-playwright-$STAMP.pid"

mkdir -p "$CAPTURE_ROOT" "$PLAYWRIGHT_VIDEO_DIR"

cleanup() {
  if [ -f "$PLAYWRIGHT_PID_FILE" ]; then
    PLAYWRIGHT_PID="$(cat "$PLAYWRIGHT_PID_FILE" || true)"
    if [ -n "${PLAYWRIGHT_PID:-}" ]; then
      kill "$PLAYWRIGHT_PID" >/dev/null 2>&1 || true
    fi
    rm -f "$PLAYWRIGHT_PID_FILE"
  fi
  if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE" || true)"
    if [ -n "${PID:-}" ]; then
      kill "$PID" >/dev/null 2>&1 || true
    fi
    rm -f "$PID_FILE"
  fi
}

trap cleanup EXIT

(
  cd "$BACKEND_ROOT"
  source .venv/bin/activate
  export STORAGE_ROOT="data/$RUN_NAME"
  export VECTOR_DATA_ROOT="data/$RUN_NAME"
  export ANSWER_PROVIDER="mlx-local"
  uvicorn app.main:app --host 127.0.0.1 --port 8000 >/tmp/jvt-demo-backend-$STAMP.log 2>&1
) &
echo $! > "$PID_FILE"

for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "Backend did not start for demo capture." >&2
  exit 1
fi

(
  sleep 1
  python3 "$SCRIPT_ROOT/playwright_demo_sequence.py" --headless --video-dir "$PLAYWRIGHT_VIDEO_DIR"
) &
echo $! > "$PLAYWRIGHT_PID_FILE"

PLAYWRIGHT_PID="$(cat "$PLAYWRIGHT_PID_FILE")"
wait "$PLAYWRIGHT_PID"

RAW_VIDEO_PATH="$(find "$PLAYWRIGHT_VIDEO_DIR" -maxdepth 1 -name '*.webm' | head -n 1)"
if [ -z "${RAW_VIDEO_PATH:-}" ]; then
  echo "Playwright capture finished but no browser video artifact was found." >&2
  exit 1
fi

ffmpeg -y -i "$RAW_VIDEO_PATH" -c:v libx264 -pix_fmt yuv420p -movflags +faststart -an "$OUTPUT_PATH" >/tmp/jvt-demo-ffmpeg-$STAMP.log 2>&1

echo "$OUTPUT_PATH"
echo "$RAW_VIDEO_PATH"
echo "$PLAYWRIGHT_VIDEO_DIR"
