#!/usr/bin/env bash
set -euo pipefail

PLIST_DEST="${HOME}/Library/LaunchAgents/com.jvt.daily-wave-prep.plist"
WORKDIR="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
SCRIPT_PATH="${WORKDIR}/outreach/tools/run_daily_wave_prep.sh"
LOG_DIR="${WORKDIR}/outreach/schedules"

mkdir -p "${HOME}/Library/LaunchAgents" "${LOG_DIR}"

cat > "${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.jvt.daily-wave-prep</string>
    <key>ProgramArguments</key>
    <array>
      <string>${SCRIPT_PATH}</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
      <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>45</integer>
      </dict>
      <dict>
        <key>Weekday</key>
        <integer>2</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>45</integer>
      </dict>
      <dict>
        <key>Weekday</key>
        <integer>3</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>45</integer>
      </dict>
      <dict>
        <key>Weekday</key>
        <integer>4</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>45</integer>
      </dict>
      <dict>
        <key>Weekday</key>
        <integer>5</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>45</integer>
      </dict>
    </array>
    <key>WorkingDirectory</key>
    <string>${WORKDIR}</string>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/daily-wave-prep.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/daily-wave-prep.stderr.log</string>
  </dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "${PLIST_DEST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_DEST}"
launchctl enable "gui/$(id -u)/com.jvt.daily-wave-prep"

echo "Installed com.jvt.daily-wave-prep. It prepares review packets every weekday at 08:45; it does not send email."
