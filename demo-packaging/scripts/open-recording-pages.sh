#!/bin/zsh

set -euo pipefail

SITE_URL="${SITE_URL:-file:///Users/c.s.d.v.r.s./Developer/Control-Host/Private-AI-Lab/JVT-Technologies/site/index.html}"
DEMO_URL="${DEMO_URL:-http://127.0.0.1:8000/demo}"

open "$SITE_URL"
open "$DEMO_URL"
