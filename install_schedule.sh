#!/usr/bin/env bash
# Install a macOS launchd plist that runs daily_report.py every day at 09:00.
# Run once: bash install_schedule.sh
# To uninstall: bash install_schedule.sh --uninstall

set -euo pipefail

PLIST_LABEL="com.jarvis.claude-token-tracker"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
SCRIPT="$PROJECT_DIR/daily_report.py"
LOG_DIR="$PROJECT_DIR/data"
HOUR=9
MINUTE=0

if [[ "${1:-}" == "--uninstall" ]]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "✓ Uninstalled $PLIST_LABEL"
    exit 0
fi

if [[ ! -f "$PYTHON" ]]; then
    echo "ERROR: venv not found at $PYTHON"
    echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

mkdir -p "$LOG_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${SCRIPT}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${HOUR}</integer>
        <key>Minute</key>
        <integer>${MINUTE}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/tracker.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/tracker_error.log</string>

    <key>RunAtLoad</key>
    <false/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "✓ Installed and loaded: $PLIST_LABEL"
echo "  Runs daily at ${HOUR}:$(printf '%02d' $MINUTE)"
echo "  Logs: $LOG_DIR/tracker.log"
echo ""
echo "To test immediately: $PYTHON $SCRIPT --dry-run"
echo "To uninstall:        bash $0 --uninstall"
