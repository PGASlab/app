# Shared helpers: pick ssh or adb from the first argument.
#   --adb               USB, via adb
#   <host>              ssh, e.g. pgas.local or arduino@192.168.1.20
# Sourced by the other scripts. Works with macOS bash 3.2.
APP_DIR="${PGAS_APP_DIR:-/home/arduino/ArduinoApps/pgas}"

if [ "${1:-}" = "" ]; then
  echo "usage: $0 <board-host>|--adb" >&2
  exit 64
fi
if [ "$1" = "--adb" ]; then
  MODE=adb
else
  MODE=ssh
  HOST="$1"
  case "$HOST" in *@*) ;; *) HOST="arduino@$HOST" ;; esac
fi

# Run a shell command on the board. adb shell sets TMPDIR=/data/local/tmp (an
# Android path that does not exist on the UNO Q), which breaks arduino-app-cli.
board() {
  if [ "$MODE" = adb ]; then adb shell "export TMPDIR=/tmp; $1"; else ssh "$HOST" "$1"; fi
}

# Stream a tar archive from stdin into a directory on the board.
board_untar() {
  if [ "$MODE" = adb ]; then
    local tmp=/tmp/pgas-deploy.tar
    cat > "${TMPDIR:-/tmp}/pgas-deploy.tar"
    adb push "${TMPDIR:-/tmp}/pgas-deploy.tar" "$tmp" >/dev/null
    adb shell "mkdir -p '$1' && tar -xf $tmp -C '$1' && rm -f $tmp"
  else
    ssh "$HOST" "mkdir -p '$1' && tar -xf - -C '$1'"
  fi
}
