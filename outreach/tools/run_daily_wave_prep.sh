#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
ENV_FILE="$ROOT/outreach/.env.local"
LOCK_DIR="$ROOT/outreach/schedules/daily-wave-prep.lock"
PYTHON_BIN="${JVT_PYTHON_BIN:-python3}"

mkdir -p "$ROOT/outreach/schedules"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
  PYTHON_BIN="${JVT_PYTHON_BIN:-$PYTHON_BIN}"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "daily wave prep already running; exiting"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

PACKET_DATE="$(date +%F)"
SCHEDULE_PATH="$ROOT/outreach/schedules/$PACKET_DATE-daily-wave.json"

"$PYTHON_BIN" "$ROOT/outreach/tools/generate_daily_wave.py" \
  --root "$ROOT" \
  --packet-date "$PACKET_DATE" \
  --limit "${JVT_DAILY_WAVE_LIMIT:-10}" \
  --reply-to-email "${JVT_REPLY_TO_EMAIL:-hello@jvt-technologies.com}" \
  --site-url "${JVT_SITE_URL:-https://jvt-technologies.com}" \
  --sender-name "${JVT_SENDER_NAME:-Chandru Vasudevan}" \
  --sender-title "${JVT_SENDER_TITLE:-Founder}" \
  --sender-company "${JVT_SENDER_COMPANY:-JVT Technologies LLC}"

if [ "${JVT_AUTO_APPROVE_CLEAN_PACKETS:-true}" = "true" ]; then
  "$PYTHON_BIN" "$ROOT/outreach/tools/auto_review_wave.py" \
    --schedule "$SCHEDULE_PATH" \
    --flagged-target "${JVT_AUTO_REVIEW_FLAGGED_TARGET:-draft}"
fi
