#!/usr/bin/env bash
# Build app/sketch/sketch.ino for an ATmega328P (Arduino Uno R3 stand-in) with
# the official Arduino AVR core, for the simavr / Wokwi simulations.
#   sim/build_avr.sh <path-to-ArduinoCore-avr> <out-dir>
# Needs: avr-gcc, avr-libc  (Ubuntu: apt install gcc-avr avr-libc;  macOS: brew tap osx-cross/avr && brew install avr-gcc)
set -euo pipefail
CORE="$1/cores/arduino"; VAR="$1/variants/standard"; OUT="$2"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$OUT/obj"
FLAGS="-mmcu=atmega328p -DF_CPU=16000000L -DARDUINO=10819 -DARDUINO_AVR_UNO -DARDUINO_ARCH_AVR -Os -ffunction-sections -fdata-sections -I$CORE -I$VAR"
{ echo '#include <Arduino.h>'; echo '#line 1 "sketch.ino"'; cat "$HERE/app/sketch/sketch.ino"; } > "$OUT/sketch.cpp"
objs=()
for f in "$CORE"/*.c; do o="$OUT/obj/$(basename "$f").o"; avr-gcc $FLAGS -std=gnu11 -c "$f" -o "$o"; objs+=("$o"); done
for f in "$CORE"/*.cpp "$OUT/sketch.cpp"; do o="$OUT/obj/$(basename "$f").o"; avr-g++ $FLAGS -std=gnu++11 -fno-exceptions -fno-threadsafe-statics -c "$f" -o "$o"; objs+=("$o"); done
for f in "$CORE"/*.S; do [ -e "$f" ] || continue; o="$OUT/obj/$(basename "$f").o"; avr-gcc $FLAGS -x assembler-with-cpp -c "$f" -o "$o"; objs+=("$o"); done
avr-gcc -mmcu=atmega328p -Os -Wl,--gc-sections -o "$OUT/pgas.elf" "${objs[@]}" -lm
avr-objcopy -O ihex -R .eeprom "$OUT/pgas.elf" "$OUT/pgas.hex"
avr-size "$OUT/pgas.elf"
