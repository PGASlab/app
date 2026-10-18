#!/bin/sh
# PGAS keep-alive, run every minute by cron on the board (installed by
# scripts/deploy.sh --boot). After a power dip or reset the App Lab autostart
# sometimes leaves the app "stopped" (the MCU flash at boot can fail), so the
# dashboard refuses connections. This restarts it. Logs to /tmp/pgas-keepalive.log.
export TMPDIR=/tmp
export PATH=/usr/local/bin:/usr/bin:/bin:$PATH
command -v arduino-app-cli >/dev/null 2>&1 || exit 0
[ -e /tmp/pgas-deploying ] && exit 0                       # deploy.sh is restarting it
pgrep -f "arduino-app-cli app start" >/dev/null 2>&1 && exit 0   # a start is in progress
# Give a fresh boot 90 s for App Lab's own autostart first.
up=$(cut -d. -f1 /proc/uptime)
[ "${up:-0}" -lt 90 ] && exit 0
if ! arduino-app-cli app list 2>/dev/null | grep "user:pgas" | grep -q running; then
  echo "$(date -u +%FT%TZ) pgas not running - starting" >> /tmp/pgas-keepalive.log
  arduino-app-cli app start user:pgas >> /tmp/pgas-keepalive.log 2>&1
fi
