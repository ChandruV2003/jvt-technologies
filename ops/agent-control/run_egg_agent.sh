#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
cd "$ROOT"

export JVT_MODEL_ROUTER_TIMEOUT_SECONDS="${JVT_MODEL_ROUTER_TIMEOUT_SECONDS:-90}"

TMP_OUT="$(mktemp)"
TMP_ERR="$(mktemp)"
cleanup() {
  rm -f "$TMP_OUT" "$TMP_ERR"
}
trap cleanup EXIT

set +e
/usr/bin/python3 "$ROOT/ops/agent-control/egg_agent.py" --max-new-tasks 6 --max-pending 12 >"$TMP_OUT" 2>"$TMP_ERR"
egg_status=$?
set -e

cat "$TMP_OUT"
cat "$TMP_ERR" >&2

if [[ "$egg_status" -ne 0 ]]; then
  /usr/bin/python3 "$ROOT/ops/agent-control/agent_repair_escalator.py" \
    --agent egg \
    --returncode "$egg_status" \
    --stdout-file "$TMP_OUT" \
    --stderr-file "$TMP_ERR" \
    --command "python3 ops/agent-control/egg_agent.py --max-new-tasks 6 --max-pending 12" \
    || true
fi

exit "$egg_status"
