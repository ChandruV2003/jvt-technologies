#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$SCRIPT_DIR/.env.local}"
REPO_ENV_FILE="${REPO_ENV_FILE:-$SCRIPT_DIR/../.env.local}"
BREW_PREFIX="/opt/homebrew/bin"
export PATH="${BREW_PREFIX}:${PATH}"

for env_file in "$LOCAL_ENV_FILE" "$REPO_ENV_FILE"; do
  if [[ -f "$env_file" ]]; then
    set -a
    source "$env_file"
    set +a
  fi
done

PROJECT_NAME="${CLOUDFLARE_PAGES_PROJECT:-jvt-technologies-site}"
ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-${CF_ACCOUNT_ID:-}}"

if [[ -n "$ACCOUNT_ID" ]]; then
  export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"
fi

if [[ -x "${BREW_PREFIX}/wrangler" ]]; then
  WRANGLER_BIN="${BREW_PREFIX}/wrangler"
elif command -v wrangler >/dev/null 2>&1; then
  WRANGLER_BIN="$(command -v wrangler)"
else
  echo "wrangler not found. Install it with Homebrew or npm before deploying." >&2
  exit 1
fi

cd "$SCRIPT_DIR/.."
set +e
DEPLOY_OUTPUT="$("${WRANGLER_BIN}" pages deploy site --project-name "$PROJECT_NAME" 2>&1)"
DEPLOY_STATUS=$?
set -e

printf '%s\n' "$DEPLOY_OUTPUT"

if [[ "$DEPLOY_STATUS" -ne 0 ]]; then
  if [[ "$DEPLOY_OUTPUT" == *"Authentication error [code: 10000]"* ]]; then
    cat >&2 <<'EOF'

Cloudflare authentication failed before the Pages project could deploy.

Known fixes:
1. Re-authenticate Wrangler on the M4:
   PATH=/opt/homebrew/bin:$PATH wrangler login

2. Or configure site/.env.local with:
   CLOUDFLARE_ACCOUNT_ID=<account id>
   CLOUDFLARE_API_TOKEN=<token with Account / Cloudflare Pages / Edit>

This is not a missing Wrangler install and not a static-site build failure.
EOF
  fi
  exit "$DEPLOY_STATUS"
fi
