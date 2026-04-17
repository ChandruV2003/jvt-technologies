#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
LEAD_DB="$ROOT/lead-pipeline/data/jvt_leads.sqlite3"
TEMPLATE="$ROOT/outreach/templates/initial-introduction.md"
OUTPUT_DIR="$ROOT/outreach/queue/draft"
ENV_FILE="${ENV_FILE:-$ROOT/outreach/.env.local}"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

REPLY_TO="${JVT_REPLY_TO_EMAIL:-hello@jvt-technologies.com}"
SITE_URL="${JVT_SITE_URL:-https://jvt-technologies.com}"
DEMO_VIDEO_URL="${JVT_DEMO_VIDEO_URL:-}"
SENDER_NAME="${JVT_SENDER_NAME:-Chandru Vasudevan}"
SENDER_TITLE="${JVT_SENDER_TITLE:-Founder, JVT Technologies}"
SENDER_COMPANY="${JVT_SENDER_COMPANY:-JVT Technologies}"

for LEAD_ID in 4 5 9 7 10; do
  python3 "$ROOT/outreach/tools/generate_draft.py" \
    --db "$LEAD_DB" \
    --lead-id "$LEAD_ID" \
    --template "$TEMPLATE" \
    --output-dir "$OUTPUT_DIR" \
    --contact-name team \
    --reply-to-email "$REPLY_TO" \
    --site-url "$SITE_URL" \
    --demo-video-url "$DEMO_VIDEO_URL" \
    --sender-name "$SENDER_NAME" \
    --sender-title "$SENDER_TITLE" \
    --sender-company "$SENDER_COMPANY"
done
