#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
cd "$ROOT"

export JVT_AI_DIRECTOR_TIMEOUT_SECONDS="${JVT_AI_DIRECTOR_TIMEOUT_SECONDS:-35}"
export JVT_AI_DIRECTOR_NUM_PREDICT="${JVT_AI_DIRECTOR_NUM_PREDICT:-180}"

/usr/bin/python3 "$ROOT/ops/agent-control/ai_director.py" --write-tasks
