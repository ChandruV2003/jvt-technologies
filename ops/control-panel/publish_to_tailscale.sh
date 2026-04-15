#!/usr/bin/env bash
set -euo pipefail

TAILSCALE_BIN="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
LOCAL_PORT="${1:-8042}"

if [[ ! -x "${TAILSCALE_BIN}" ]]; then
  echo "Tailscale CLI not found at ${TAILSCALE_BIN}" >&2
  exit 1
fi

DNS_NAME="$("${TAILSCALE_BIN}" status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"

"${TAILSCALE_BIN}" serve --bg "${LOCAL_PORT}"

echo "Tailscale Serve configured."
echo "Tailnet URL: https://${DNS_NAME}/"
echo "Local origin: http://127.0.0.1:${LOCAL_PORT}/"
