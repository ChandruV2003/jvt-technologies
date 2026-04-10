#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR/.."
wrangler pages deploy site --project-name jvt-technologies-site
