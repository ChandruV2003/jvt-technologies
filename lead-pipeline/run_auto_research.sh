#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTREACH_ENV="$ROOT_DIR/outreach/.env.local"
PYTHON_BIN="${JVT_PYTHON_BIN:-python3}"
LOCK_DIR="$ROOT_DIR/lead-pipeline/state/auto-research.lock"

mkdir -p "$ROOT_DIR/lead-pipeline/state"

if [ -f "$OUTREACH_ENV" ]; then
  set -a
  source "$OUTREACH_ENV"
  set +a
  PYTHON_BIN="${JVT_PYTHON_BIN:-$PYTHON_BIN}"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "auto_research already running; exiting"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

export JVT_RESEARCH_MODEL_SCREEN="${JVT_RESEARCH_MODEL_SCREEN:-optional}"
export JVT_RESEARCH_MODEL_SCREEN_PROFILES="${JVT_RESEARCH_MODEL_SCREEN_PROFILES:-strong,reviewer}"
export JVT_RESEARCH_MODEL_SCREEN_TIMEOUT="${JVT_RESEARCH_MODEL_SCREEN_TIMEOUT:-900}"

"$PYTHON_BIN" "$ROOT_DIR/lead-pipeline/tools/auto_research.py" \
  --root "$ROOT_DIR" \
  --queries-per-run "${JVT_RESEARCH_QUERIES_PER_RUN:-8}" \
  --results-per-query "${JVT_RESEARCH_RESULTS_PER_QUERY:-10}" \
  --max-new-leads "${JVT_RESEARCH_MAX_NEW_LEADS:-15}" \
  --draft-limit "${JVT_RESEARCH_DRAFT_LIMIT:-0}" \
  "$@"
