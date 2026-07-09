#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
LABEL="com.jvt.watchdog"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/ops/watchdog/state"
cp "$ROOT/ops/watchdog/$LABEL.plist.example" "$PLIST"
chmod 644 "$PLIST"
chmod +x "$ROOT/ops/watchdog/run_watchdog.sh"

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
launchctl print "gui/$(id -u)/$LABEL" | sed -n '1,80p'
