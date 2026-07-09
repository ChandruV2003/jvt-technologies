#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
ENV_FILE="$ROOT/outreach/.env.local"
LOCK_DIR="$ROOT/outreach/schedules/followup-prep.lock"
PYTHON_BIN="python3"

mkdir -p "$ROOT/outreach/schedules/followups"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

if [ -n "${JVT_PYTHON_BIN:-}" ] && [ -x "$JVT_PYTHON_BIN" ]; then
  PYTHON_BIN="$JVT_PYTHON_BIN"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "follow-up prep already running; exiting"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

"$PYTHON_BIN" "$ROOT/outreach/tools/generate_followups.py" \
  --root "$ROOT" \
  --min-age-days "${JVT_FOLLOWUP_MIN_AGE_DAYS:-4}" \
  --limit "${JVT_FOLLOWUP_PREP_LIMIT:-20}" \
  --output-queue "${JVT_FOLLOWUP_OUTPUT_QUEUE:-review}" \
  --reply-to-email "${JVT_REPLY_TO_EMAIL:-hello@jvt-technologies.com}" \
  --site-url "${JVT_SITE_URL:-https://jvt-technologies.com}" \
  --sender-name "${JVT_SENDER_NAME:-Chandru Vasudevan}" \
  --sender-title "${JVT_SENDER_TITLE:-Founder}" \
  --sender-company "${JVT_SENDER_COMPANY:-JVT Technologies LLC}" \
  --write

