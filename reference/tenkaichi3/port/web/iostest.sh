#!/bin/bash
# The iPhone test: the game in Safari on an iOS Simulator, reporting to the test server (port/web/serve.mjs must be
# running: node port/web/serve.mjs 4500 disc/bt3-usa.iso).
#   port/web/iostest.sh [seconds] [extra query]      e.g.  port/web/iostest.sh 90 "&env=BT3_DEMO=1"
# Opens http://127.0.0.1:4500/?disc=/disc.iso&telemetry=1&hud=1<extra> on the booted simulator (boots an iPhone 17
# Pro if none is), waits, saves a screenshot to port/build/ios.png and prints port/web/telemetry.py's summary.
set -e
cd "$(dirname "$0")/../.."
secs=${1:-60}; extra=${2:-}
if ! xcrun simctl list devices booted | grep -q Booted; then
  xcrun simctl boot "iPhone 17 Pro"; open -a Simulator; sleep 8
fi
: > port/build/telemetry.log
xcrun simctl terminate booted com.apple.mobilesafari 2>/dev/null || true
xcrun simctl openurl booted "http://127.0.0.1:4500/?disc=/disc.iso&telemetry=1&hud=1${extra}"
sleep "$secs"
xcrun simctl io booted screenshot port/build/ios.png >/dev/null 2>&1
python3 port/web/telemetry.py
