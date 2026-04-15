#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
OUTREACH_ROOT="$ROOT/outreach"
MAILBOX_ROOT="$OUTREACH_ROOT/mailbox-agent"
CONTROL_ROOT="$ROOT/ops/agent-control"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$OUTREACH_ROOT/.env.local}"
MAILBOX_LOCAL_ENV_FILE="${MAILBOX_LOCAL_ENV_FILE:-$MAILBOX_ROOT/.env.local}"

if [ -f "$LOCAL_ENV_FILE" ]; then
  set -a
  source "$LOCAL_ENV_FILE"
  set +a
fi

PYTHON_BIN="${JVT_PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage:
  reviewed_outreach.sh wave
  reviewed_outreach.sh move <stem> <from> <to>
  reviewed_outreach.sh dry-run <stem>
  reviewed_outreach.sh send <stem>
  reviewed_outreach.sh inbox-once
  reviewed_outreach.sh draft-reply <message-json>
  reviewed_outreach.sh draft-reply-fast <message-json>
  reviewed_outreach.sh draft-reply-strong <message-json>
  reviewed_outreach.sh status
  reviewed_outreach.sh request-decision <category> <title> <recommended-action>
  reviewed_outreach.sh log-decision <stem> <approved|rejected|executed> [note]
EOF
}

command_name="${1:-}"
if [ -z "$command_name" ]; then
  usage
  exit 1
fi

shift

case "$command_name" in
  wave)
    exec zsh "$OUTREACH_ROOT/tools/generate_first_wave.sh"
    ;;
  move)
    exec "$PYTHON_BIN" "$OUTREACH_ROOT/tools/move_packet.py" --stem "$1" --from "$2" --to "$3"
    ;;
  dry-run)
    exec "$PYTHON_BIN" "$OUTREACH_ROOT/tools/send_approved.py" --stem "$1"
    ;;
  send)
    exec "$PYTHON_BIN" "$OUTREACH_ROOT/tools/send_approved.py" --stem "$1" --send
    ;;
  inbox-once)
    if [ -f "$MAILBOX_LOCAL_ENV_FILE" ]; then
      set -a
      source "$MAILBOX_LOCAL_ENV_FILE"
      set +a
    fi
    exec "$PYTHON_BIN" "$MAILBOX_ROOT/mailbox_listener.py" --once
    ;;
  draft-reply)
    if [ -f "$MAILBOX_LOCAL_ENV_FILE" ]; then
      set -a
      source "$MAILBOX_LOCAL_ENV_FILE"
      set +a
    fi
    exec "$PYTHON_BIN" "$MAILBOX_ROOT/draft_reply.py" --message-json "$1"
    ;;
  draft-reply-fast)
    if [ -f "$MAILBOX_LOCAL_ENV_FILE" ]; then
      set -a
      source "$MAILBOX_LOCAL_ENV_FILE"
      set +a
    fi
    exec "$PYTHON_BIN" "$MAILBOX_ROOT/draft_reply.py" --message-json "$1" --model-profile fast
    ;;
  draft-reply-strong)
    if [ -f "$MAILBOX_LOCAL_ENV_FILE" ]; then
      set -a
      source "$MAILBOX_LOCAL_ENV_FILE"
      set +a
    fi
    exec "$PYTHON_BIN" "$MAILBOX_ROOT/draft_reply.py" --message-json "$1" --model-profile strong
    ;;
  status)
    exec "$PYTHON_BIN" "$CONTROL_ROOT/status_snapshot.py"
    ;;
  request-decision)
    exec "$PYTHON_BIN" "$CONTROL_ROOT/create_decision_packet.py" "$1" "$2" "$3"
    ;;
  log-decision)
    if [ "$#" -ge 3 ]; then
      exec "$PYTHON_BIN" "$CONTROL_ROOT/log_decision.py" "$1" "$2" "$3"
    fi
    exec "$PYTHON_BIN" "$CONTROL_ROOT/log_decision.py" "$1" "$2"
    ;;
  *)
    usage
    exit 1
    ;;
esac
