#!/usr/bin/env bash
# Build the sketch's UNO Q code path against the emulated MCU API.
#   sim/unoq/build.sh native <out-dir>   -> <out-dir>/unoq_native   (g++)
#   sim/unoq/build.sh wasm   <out-dir>   -> <out-dir>/unoq_mcu.js   (emscripten, single file)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
mkdir -p "$2"
SK="$2/sketch_unoq.cpp"
{ echo '#include "unoq_hal.h"'; echo '#line 1 "sketch.ino"'; cat "$ROOT/app/sketch/sketch.ino"; } > "$SK"
case "$1" in
  native)
    g++ -std=c++17 -O2 -Wall -I"$HERE/hal" "$SK" "$HERE/hal/unoq_hal.cpp" "$HERE/native_main.cpp" -o "$2/unoq_native" ;;
  wasm)
    em++ -std=c++17 -O2 -I"$HERE/hal" "$SK" "$HERE/hal/unoq_hal.cpp" "$HERE/wasm_glue.cpp" -o "$2/unoq_mcu.js" \
      -sMODULARIZE=1 -sEXPORT_NAME=UnoQMcu -sSINGLE_FILE=1 -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=web,node \
      -sEXPORTED_FUNCTIONS=_hal_setup,_hal_run_us,_hal_time_ms,_hal_set_module,_hal_set_env,_hal_set_dht_connected,_hal_bridge_draw,_malloc,_free \
      -sEXPORTED_RUNTIME_METHODS=ccall,cwrap,HEAPU8,UTF8ToString ;;
  js)
    # Same as wasm, but compiled to plain JavaScript (wasm2js) for hosts whose
    # content-security policy does not allow WebAssembly.
    em++ -std=c++17 -O2 -I"$HERE/hal" "$SK" "$HERE/hal/unoq_hal.cpp" "$HERE/wasm_glue.cpp" -o "$2/unoq_mcu_js.js" \
      -sWASM=0 -sSINGLE_FILE=1 -sMODULARIZE=1 -sEXPORT_NAME=UnoQMcu -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=web,node \
      -sEXPORTED_FUNCTIONS=_hal_setup,_hal_run_us,_hal_time_ms,_hal_set_module,_hal_set_env,_hal_set_dht_connected,_hal_bridge_draw,_malloc,_free \
      -sEXPORTED_RUNTIME_METHODS=ccall,cwrap,HEAPU8,UTF8ToString ;;
  *) echo "usage: $0 native|wasm|js <out-dir>" >&2; exit 64 ;;
esac
echo "built $1 -> $2"
