#!/bin/zsh

set -euo pipefail

DEMO_URL="${DEMO_URL:-http://127.0.0.1:8000}"

curl -s -X POST "$DEMO_URL/demo/reset"
echo
curl -s -X POST "$DEMO_URL/demo/sample-pack"
echo
