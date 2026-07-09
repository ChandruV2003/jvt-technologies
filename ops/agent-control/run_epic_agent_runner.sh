#!/usr/bin/env zsh
set -euo pipefail

cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies
exec /usr/bin/python3 ops/agent-control/epic_agent_runner.py --max-epics 1
