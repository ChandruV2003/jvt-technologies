#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
OUTREACH_ROOT="$ROOT/outreach"
MAILBOX_ROOT="$OUTREACH_ROOT/mailbox-agent"

usage() {
  cat <<'EOF'
Usage:
  reviewed_outreach.sh wave
  reviewed_outreach.sh move <stem> <from> <to>
  reviewed_outreach.sh dry-run <stem>
  reviewed_outreach.sh send <stem>
  reviewed_outreach.sh inbox-once
  reviewed_outreach.sh draft-reply <message-json>
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
    exec python3 "$OUTREACH_ROOT/tools/move_packet.py" --stem "$1" --from "$2" --to "$3"
    ;;
  dry-run)
    exec python3 "$OUTREACH_ROOT/tools/send_approved.py" --stem "$1"
    ;;
  send)
    exec python3 "$OUTREACH_ROOT/tools/send_approved.py" --stem "$1" --send
    ;;
  inbox-once)
    exec python3 "$MAILBOX_ROOT/mailbox_listener.py" --once
    ;;
  draft-reply)
    exec python3 "$MAILBOX_ROOT/draft_reply.py" --message-json "$1"
    ;;
  *)
    usage
    exit 1
    ;;
esac
