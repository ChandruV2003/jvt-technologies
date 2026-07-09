#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${BACKEND_ROOT}"

if [[ ! -x "./.venv/bin/python" ]]; then
  echo "Missing backend virtual environment at ${BACKEND_ROOT}/.venv" >&2
  exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-0}"

ARGS=("./.venv/bin/python" "-m" "uvicorn" "app.main:app" "--host" "${HOST}" "--port" "${PORT}")

case "${RELOAD}" in
  1|true|TRUE|yes|YES)
    ARGS+=("--reload")
    ;;
esac

exec "${ARGS[@]}"
