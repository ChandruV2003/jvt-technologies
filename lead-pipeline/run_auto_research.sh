#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTREACH_ENV="$ROOT_DIR/outreach/.env.local"
PYTHON_BIN="${JVT_PYTHON_BIN:-python3}"
LOCK_DIR="$ROOT_DIR/lead-pipeline/state/auto-research.lock"
LOCK_PID_FILE="$LOCK_DIR/pid"

mkdir -p "$ROOT_DIR/lead-pipeline/state"

if [ -f "$OUTREACH_ENV" ]; then
  set -a
  source "$OUTREACH_ENV"
  set +a
  PYTHON_BIN="${JVT_PYTHON_BIN:-$PYTHON_BIN}"
fi

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_PID_FILE"
    return 0
  fi

  local lock_pid=""
  if [ -f "$LOCK_PID_FILE" ]; then
    lock_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
  fi

  if [[ "$lock_pid" == <-> ]] && kill -0 "$lock_pid" 2>/dev/null; then
    echo "auto_research already running; exiting"
    return 1
  fi

  local stale_lock="${LOCK_DIR}.stale.$$"
  if ! mv "$LOCK_DIR" "$stale_lock" 2>/dev/null; then
    echo "auto_research lock changed during recovery; exiting"
    return 1
  fi
  rm -rf "$stale_lock"

  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "auto_research lock reacquired by another process; exiting"
    return 1
  fi
  printf '%s\n' "$$" > "$LOCK_PID_FILE"
  echo "recovered stale auto_research lock"
}

cleanup_lock() {
  local lock_pid=""
  if [ -f "$LOCK_PID_FILE" ]; then
    lock_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
  fi
  if [ "$lock_pid" = "$$" ]; then
    rm -rf "$LOCK_DIR"
  fi
}

if ! acquire_lock; then
  exit 0
fi
trap cleanup_lock EXIT

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

if [ "${JVT_RESEARCH_PACKET_PREP:-true}" = "true" ]; then
  "$PYTHON_BIN" "$ROOT_DIR/outreach/tools/prepare_fresh_research_packets.py" \
    --root "$ROOT_DIR" \
    --max-packets "${JVT_RESEARCH_PACKET_PREP_LIMIT:-5}"
fi
