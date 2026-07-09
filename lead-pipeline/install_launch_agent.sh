#!/usr/bin/env bash
set -euo pipefail

PLIST_DEST="${HOME}/Library/LaunchAgents/com.jvt.lead-research.plist"
WORKDIR="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
SCRIPT_PATH="${WORKDIR}/lead-pipeline/run_auto_research.sh"
LOG_DIR="${WORKDIR}/lead-pipeline/state"

mkdir -p "${HOME}/Library/LaunchAgents" "${LOG_DIR}"

cat > "${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.jvt.lead-research</string>
    <key>ProgramArguments</key>
    <array>
      <string>${SCRIPT_PATH}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>WorkingDirectory</key>
    <string>${WORKDIR}</string>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/lead-research.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/lead-research.stderr.log</string>
  </dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "${PLIST_DEST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_DEST}"
launchctl enable "gui/$(id -u)/com.jvt.lead-research"
launchctl kickstart -k "gui/$(id -u)/com.jvt.lead-research"

echo "Installed and started com.jvt.lead-research"
