#!/usr/bin/env zsh
set -euo pipefail

LABEL="com.jvt.epic-agent"
ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
INTERVAL_SECONDS="14400"

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>${ROOT}/ops/agent-control/run_epic_agent_runner.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>StartInterval</key>
  <integer>${INTERVAL_SECONDS}</integer>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${ROOT}/ops/agent-control/state/epic-agent.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/ops/agent-control/state/epic-agent.err.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
launchctl print "gui/$(id -u)/${LABEL}" | egrep "state|program|last exit code" || true
