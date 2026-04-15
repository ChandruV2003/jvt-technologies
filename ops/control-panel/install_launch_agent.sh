#!/usr/bin/env bash
set -euo pipefail

PLIST_DEST="${HOME}/Library/LaunchAgents/com.jvt.control-panel.plist"
WORKDIR="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
SCRIPT_PATH="${WORKDIR}/ops/control-panel/run_control_panel.sh"

mkdir -p "${HOME}/Library/LaunchAgents"

cat > "${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.jvt.control-panel</string>
    <key>ProgramArguments</key>
    <array>
      <string>${SCRIPT_PATH}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
      <key>HOST</key>
      <string>127.0.0.1</string>
      <key>PORT</key>
      <string>8042</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>${WORKDIR}</string>
    <key>StandardOutPath</key>
    <string>${WORKDIR}/ops/control-panel/control-panel.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${WORKDIR}/ops/control-panel/control-panel.stderr.log</string>
  </dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "${PLIST_DEST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_DEST}"
launchctl enable "gui/$(id -u)/com.jvt.control-panel"
launchctl kickstart -k "gui/$(id -u)/com.jvt.control-panel"

echo "Installed and started com.jvt.control-panel"
