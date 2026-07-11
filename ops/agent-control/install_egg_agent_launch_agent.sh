#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
LABEL="com.jvt.egg-agent"
OLD_LABEL="com.jvt.mythos-agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
OLD_PLIST="$HOME/Library/LaunchAgents/$OLD_LABEL.plist"
LOG_DIR="$ROOT/ops/agent-control/state"

mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$ROOT/ops/agent-control/run_egg_agent.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>900</integer>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/egg-agent.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/egg-agent.err.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$OLD_PLIST" >/dev/null 2>&1 || true
rm -f "$OLD_PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "$PLIST"
