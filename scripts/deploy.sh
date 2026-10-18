#!/usr/bin/env bash
# Deploy PGAS to the UNO Q and (re)start it.  Run on the Mac:
#   scripts/deploy.sh pgas.local          # over Wi-Fi (ssh)
#   scripts/deploy.sh --adb               # over USB
#   scripts/deploy.sh pgas.local --boot   # also start PGAS automatically at power-on
#
# Copies app.yaml, the sketch, python/main.py, the pgas package, the web
# dashboard (assets/, served by the web_ui brick on port 7000) and models/
# into ~/ArduinoApps/pgas. Never touches the board's data/ folder.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/_target.sh
BOOT=0
[ "${2:-}" = "--boot" ] && BOOT=1

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/python" "$STAGE/models"
cp app/app.yaml app/keepalive.sh "$STAGE/"
cp -R app/sketch "$STAGE/"
cp -R app/assets "$STAGE/assets"   # web_ui brick serves /app/assets
cp app/python/main.py app/python/requirements.txt "$STAGE/python/"
cp -R pgas "$STAGE/python/pgas"
find "$STAGE" -name '__pycache__' -prune -exec rm -rf {} +
for f in models/pgas_classifier.onnx models/model_card.json models/pgas_bag.onnx models/pgas_bag_card.json; do
  [ -f "$f" ] && cp "$f" "$STAGE/models/"
done
[ -f "$STAGE/models/pgas_classifier.onnx" ] || echo "note: no trained model yet - hood captures will record but not grade"

echo "copying to $APP_DIR ..."
# COPYFILE_DISABLE stops macOS tar from adding ._ resource-fork files.
(cd "$STAGE" && COPYFILE_DISABLE=1 tar -cf - .) | board_untar "$APP_DIR"
board "mkdir -p $APP_DIR/data/raw $APP_DIR/data/jobs/pending $APP_DIR/data/jobs/status"

echo "starting user:pgas (first start compiles the sketch and installs Python packages; needs internet once) ..."
# Flashing the MCU sometimes fails once with "Error requesting gpio line swdio"
# (the SWD lines are still held right after the app stops); retry once.
board "touch /tmp/pgas-deploying"   # pauses the keep-alive while we restart the app
if ! board "arduino-app-cli app stop user:pgas >/dev/null 2>&1 || true; sleep 3; arduino-app-cli app start user:pgas"; then
  echo "start failed - retrying once in 10 s ..."
  sleep 10
  board "arduino-app-cli app start user:pgas" || { board "rm -f /tmp/pgas-deploying"; exit 1; }
fi
board "rm -f /tmp/pgas-deploying"
if [ "$BOOT" = 1 ]; then
  board "arduino-app-cli properties set default user:pgas"
  # Keep-alive: every minute, restart PGAS if a reset left it stopped.
  board "chmod +x $APP_DIR/keepalive.sh; (crontab -l 2>/dev/null | grep -v pgas-keepalive; echo '* * * * * $APP_DIR/keepalive.sh # pgas-keepalive') | crontab - || echo 'note: crontab unavailable, keep-alive not installed'"
  echo "PGAS will start automatically at power-on (and is restarted within a minute if it stops)."
fi
echo "done. Follow the app log with:"
if [ "$MODE" = adb ]; then
  echo "  adb shell arduino-app-cli app logs user:pgas --follow"
else
  echo "  ssh $HOST arduino-app-cli app logs user:pgas --follow"
fi
