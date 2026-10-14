#!/usr/bin/env bash
# Copy captures (and self-test logs) from the board into this repo.  Run on the Mac:
#   scripts/pull-data.sh pgas.local    |    scripts/pull-data.sh --adb
# Existing local files are never overwritten.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/_target.sh
mkdir -p data/raw data/selftest data/board-logs
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [ "$MODE" = adb ]; then
  adb pull "$APP_DIR/data/raw/." "$TMP/raw" >/dev/null
  adb pull "$APP_DIR/data/selftest/." "$TMP/selftest" >/dev/null 2>&1 || true
else
  ssh "$HOST" "cd $APP_DIR/data && tar -cf - raw selftest 2>/dev/null || tar -cf - raw" | tar -xf - -C "$TMP"
fi
for sub in raw selftest; do
  [ -d "$TMP/$sub" ] || continue
  for f in "$TMP/$sub"/*; do
    [ -e "$f" ] || continue
    dest="data/$sub/$(basename "$f")"
    if [ ! -e "$dest" ]; then cp "$f" "$dest"; echo "new  $dest"
    elif ! cmp -s "$f" "$dest"; then
      # Growing continuous capture: the board copy is the newer superset.
      case "$f" in *_continuous_*) cp "$f" "$dest"; echo "upd  $dest" ;; *) echo "skip $dest (differs locally)";; esac
    fi
  done
done
