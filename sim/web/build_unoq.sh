#!/usr/bin/env bash
# Build sim/web/pgas-unoq-sim.html (self-contained, offline):
#   sim/unoq/build.sh wasm build/unoq && sim/web/build_unoq.sh build/unoq/unoq_mcu.js
set -euo pipefail
cd "$(dirname "$0")"
MCU="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
[ -d node_modules/esbuild ] || npm install --no-save --silent esbuild@0.24.0
npx esbuild src/unoq.js --bundle --format=iife --minify --outfile=build/unoq_bundle.js --log-level=warning
python3 - "$MCU" <<'PY'
import sys, pathlib
mcu = pathlib.Path(sys.argv[1]).read_text().replace("</script", "<\\/script")
mcu += "\nwindow.UnoQMcu = UnoQMcu;\n"
bundle = pathlib.Path("build/unoq_bundle.js").read_text().replace("</script", "<\\/script")
html = pathlib.Path("unoq_template.html").read_text()
out = html.replace("/*MCU*/", mcu).replace("/*BUNDLE*/", bundle)
pathlib.Path("pgas-unoq-sim.html").write_text(out)
print(f"wrote sim/web/pgas-unoq-sim.html ({len(out)//1024} KB)")
PY
