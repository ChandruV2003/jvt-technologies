#!/usr/bin/env bash
set -euo pipefail

BACKEND_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/products/Private-AI-Lab/apps/private-doc-intel-demo/backend"
SCRIPT_PATH="${BACKEND_ROOT}/tools/run_local_backend.sh"
PLIST_DEST="${HOME}/Library/LaunchAgents/com.jvt.private-doc-intel-demo.plist"

mkdir -p "${HOME}/Library/LaunchAgents"

cat > "${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.jvt.private-doc-intel-demo</string>
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
      <string>8000</string>
      <key>RELOAD</key>
      <string>0</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>${BACKEND_ROOT}</string>
    <key>StandardOutPath</key>
    <string>${BACKEND_ROOT}/private-doc-intel-demo.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${BACKEND_ROOT}/private-doc-intel-demo.stderr.log</string>
  </dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "${PLIST_DEST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_DEST}"
launchctl enable "gui/$(id -u)/com.jvt.private-doc-intel-demo"
launchctl kickstart -k "gui/$(id -u)/com.jvt.private-doc-intel-demo"

echo "Installed and started com.jvt.private-doc-intel-demo"
