#!/bin/zsh

set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
LABEL="com.jvt.followup-prep"
SOURCE="$ROOT/outreach/tools/$LABEL.plist.example"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$SOURCE" ]; then
  echo "Missing launch agent template: $SOURCE" >&2
  exit 1
fi

chmod +x "$ROOT/outreach/tools/run_followup_prep.sh"
mkdir -p "$HOME/Library/LaunchAgents"
cp "$SOURCE" "$TARGET"

launchctl bootout "gui/$(id -u)" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true

echo "Installed $LABEL at $TARGET"

