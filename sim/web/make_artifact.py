"""Turn the built pgas-unoq-sim.html into a page body for a hosted artifact
(the host adds the <html>/<head>/<body> skeleton itself).
    python3 sim/web/make_artifact.py <built.html> <out.html>"""
import re
import sys
from pathlib import Path

s = Path(sys.argv[1]).read_text()
s = re.sub(r'^<!doctype html>\s*<html[^>]*>\s*<head>\s*<meta charset="utf-8">\s*<meta name="viewport"[^>]*>\s*', "", s)
s = s.replace("</head>\n<body>\n", "", 1)
s = re.sub(r"</body>\s*</html>\s*$", "\n", s)
assert s.lstrip().startswith("<title>"), s[:200]
Path(sys.argv[2]).write_text(s)
print(f"wrote {sys.argv[2]} ({len(s) // 1024} KB)")
