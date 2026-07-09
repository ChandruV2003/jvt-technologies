#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/jvt-inbound-voice-agent"
PLIST_NAME="com.jvt.inbound-voice-agent.plist"
SOURCE_PLIST="$APP_ROOT/com.jvt.inbound-voice-agent.plist.example"
TARGET_PLIST="$HOME/Library/LaunchAgents/$PLIST_NAME"

mkdir -p "$HOME/Library/LaunchAgents" "$APP_ROOT/data"
cp "$SOURCE_PLIST" "$TARGET_PLIST"

launchctl unload "$TARGET_PLIST" >/dev/null 2>&1 || true
launchctl load "$TARGET_PLIST"
launchctl start "com.jvt.inbound-voice-agent"

echo "Installed and started com.jvt.inbound-voice-agent"
echo "Health: http://127.0.0.1:8066/health"

