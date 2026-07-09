#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
cd "$ROOT"

TMP_OUT="$(mktemp)"
TMP_ERR="$(mktemp)"
cleanup() {
  rm -f "$TMP_OUT" "$TMP_ERR"
}
trap cleanup EXIT

set +e
/usr/bin/python3 "$ROOT/ops/agent-control/local_task_runner.py" --max-tasks "${JVT_LOCAL_TASK_MAX:-3}" >"$TMP_OUT" 2>"$TMP_ERR"
runner_status=$?
set -e

cat "$TMP_OUT"
cat "$TMP_ERR" >&2

if [[ "$runner_status" -ne 0 ]] && grep -q "Local task runner is already running" "$TMP_ERR"; then
  echo '{"ok": true, "processed_count": 0, "reason": "runner_already_active"}'
  exit 0
fi

exit "$runner_status"
