#!/bin/zsh
set -euo pipefail

ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
PLIST="$HOME/Library/LaunchAgents/com.jvt.m4-tcp-pressure-watchdog.plist"
LOG_DIR="$ROOT/ops/agent-control/logs"

mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.jvt.m4-tcp-pressure-watchdog</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/ops/agent-control/run_m4_tcp_pressure_watchdog.sh</string>
  </array>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/m4-tcp-pressure-watchdog.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/m4-tcp-pressure-watchdog.err.log</string>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.jvt.m4-tcp-pressure-watchdog"
launchctl print "gui/$(id -u)/com.jvt.m4-tcp-pressure-watchdog" | sed -n '1,80p'
