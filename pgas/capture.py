"""PGAS capture tool.

On the board (the PGAS app must be running):

    cd ~/ArduinoApps/pgas/python
    python3 -m pgas.capture --mode hood --label fresh_chicken
    python3 -m pgas.capture --mode continuous --label chicken_room_temp [--hours 48]
    python3 -m pgas.capture --stop              # end a continuous recording
    python3 -m pgas.capture --status            # what is running
    python3 -m pgas.capture --selftest          # same as python3 -m pgas.selftest

From the Mac, add --host <board>.local (ssh) or --adb (USB) and the same
command runs on the board.

Hood mode follows the LED matrix: A = ambient baseline (30 s), M = move the
box over the food, H = hold it there (60 s), V = lift it and vent until the
readings are back to baseline. Then the matrix shows the grade and the
advice is printed.

Standard library only (runs on the board's host Python, no venv needed).
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

from . import config, jobs

LABEL_HELP = ("lowercase words joined by '_'. Hood labels starting with fresh_, spoiling_, spoiled_ "
              "or swill_ are used as training labels (see docs/labeling.md)")


def _check_label(label: str) -> str:
    import re

    if not re.match(r"^[a-z0-9]+(?:_[a-z0-9]+)*$", label or ""):
        raise argparse.ArgumentTypeError(f"bad label {label!r}: {LABEL_HELP}")
    return label


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m pgas.capture", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--mode", choices=("hood", "continuous"))
    what.add_argument("--stop", action="store_true", help="stop the running continuous capture")
    what.add_argument("--status", action="store_true", help="show the most recent jobs")
    what.add_argument("--selftest", action="store_true", help="run the hardware self-test")
    ap.add_argument("--label", type=_check_label, help=LABEL_HELP)
    ap.add_argument("--hours", type=float, help="continuous mode: stop after this many hours")
    ap.add_argument("--no-llm", action="store_true", help="hood mode: use rule-based advice only")
    ap.add_argument("--host", help="run on the board over ssh, e.g. pgas.local or arduino@192.168.1.20")
    ap.add_argument("--adb", action="store_true", help="run on the board over USB with adb")
    ap.add_argument("--app-dir", default="/home/arduino/ArduinoApps/pgas",
                    help="app folder on the board (remote use)")
    ap.add_argument("--jobs-dir", type=Path, default=config.JOBS_DIR, help=argparse.SUPPRESS)
    return ap


def remote_command(argv: list[str], a: argparse.Namespace) -> list[str]:
    """Rebuild the command to run on the board, minus the remote flags."""
    skip_next = False
    rest = []
    for x in argv:
        if skip_next:
            skip_next = False
            continue
        if x in ("--host", "--app-dir"):
            skip_next = True
            continue
        if x == "--adb" or x.startswith("--host=") or x.startswith("--app-dir="):
            continue
        rest.append(x)
    inner = f"cd {shlex.quote(a.app_dir)}/python && python3 -m pgas.capture " + " ".join(shlex.quote(x) for x in rest)
    if a.adb:
        return ["adb", "shell", inner]
    host = a.host if "@" in a.host else f"arduino@{a.host}"
    return ["ssh", "-t", host, inner]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.mode and not a.label:
        ap.error("--label is required with --mode")

    if a.host or a.adb:
        cmd = remote_command(argv, a)
        print("$ " + " ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
        return subprocess.call(cmd)

    if a.status:
        status_dir = a.jobs_dir / "status"
        for p in sorted(status_dir.glob("*.json"))[-5:]:
            st = json.loads(p.read_text())
            last = st["lines"][-1] if st["lines"] else ""
            print(f"{st['id']}  {st['kind']:10s} {st['state']:8s} {last}")
        return 0

    if a.stop:
        job_id = jobs.submit(a.jobs_dir, "stop")
    elif a.selftest:
        job_id = jobs.submit(a.jobs_dir, "selftest")
    else:
        params = {"label": a.label}
        if a.mode == "continuous" and a.hours:
            params["hours"] = a.hours
        if a.no_llm:
            params["use_llm"] = False
        job_id = jobs.submit(a.jobs_dir, a.mode, **params)

    detach = None
    if a.mode == "continuous":
        # Continuous runs for hours: return once recording has started.
        detach = lambda st: any("recording to" in ln for ln in st["lines"])
    try:
        st = jobs.follow(a.jobs_dir, job_id, detach_when=detach)
    except KeyboardInterrupt:
        print("\n(job keeps running on the board; stop a continuous capture with --stop)")
        return 130
    except TimeoutError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if st["state"] == "running":
        print("continuous capture is running on the board; stop it with: python3 -m pgas.capture --stop")
        return 0
    if st.get("result") is not None and a.mode == "hood":
        print(json.dumps(st["result"], indent=2))
    return 0 if st["state"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
