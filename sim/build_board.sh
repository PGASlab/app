#!/usr/bin/env bash
# Build the simavr virtual board.  sim/build_board.sh <out-dir>
# Needs simavr headers/lib (Ubuntu: apt install simavr libsimavr-dev libelf-dev).
set -euo pipefail
mkdir -p "$1"
gcc -O2 -Wall -o "$1/pgas_board" "$(dirname "$0")/simavr/pgas_board.c" -lsimavr -lelf
