#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$SCRIPT_DIR/.env.local}"

if [ -f "$LOCAL_ENV_FILE" ]; then
  set -a
  source "$LOCAL_ENV_FILE"
  set +a
fi

exec python3 "$SCRIPT_DIR/mailbox_listener.py"
