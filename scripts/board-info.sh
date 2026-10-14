#!/usr/bin/env bash
# Print the facts PGAS needs about the board (RAM decides the LLM).
# Run on the Mac:  scripts/board-info.sh pgas.local   |   scripts/board-info.sh --adb
set -euo pipefail
. "$(dirname "$0")/_target.sh"
board 'echo "== uname"; uname -a; echo "== memory"; free -h; echo "== disk"; df -h / /home 2>/dev/null;
echo "== python"; python3 --version; echo "== os"; cat /etc/os-release | head -3;
echo "== app cli"; arduino-app-cli version 2>/dev/null || true;
echo "== apps"; arduino-app-cli app list 2>/dev/null || true;
echo "== models"; arduino-app-cli model list 2>/dev/null || true;
echo "== network"; hostname; hostname -I'
