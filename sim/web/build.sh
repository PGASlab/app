#!/usr/bin/env bash
# Build sim/web/pgas-circuit-sim.html: one self-contained page with the
# avr8js bundle and the firmware hex inlined (works offline, file://).
#   sim/web/build.sh <pgas.hex>
# Needs node + npm (installs avr8js@0.21.0 and esbuild@0.24.0 into sim/web/node_modules).
set -euo pipefail
cd "$(dirname "$0")"
HEX="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
[ -d node_modules/avr8js ] || npm install --no-save --silent avr8js@0.21.0 esbuild@0.24.0
npx esbuild src/main.js --bundle --format=iife --minify --outfile=build/bundle.js --log-level=warning
python3 - "$HEX" <<'PY'
import sys, pathlib
hexs = pathlib.Path(sys.argv[1]).read_text()
html = pathlib.Path("template.html").read_text()
bundle = pathlib.Path("build/bundle.js").read_text().replace("</script", "<\\/script")
out = html.replace("/*HEX*/", hexs).replace("/*BUNDLE*/", bundle)
pathlib.Path("pgas-circuit-sim.html").write_text(out)
print(f"wrote sim/web/pgas-circuit-sim.html ({len(out)//1024} KB)")
PY
