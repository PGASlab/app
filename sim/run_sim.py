"""End-to-end simulation: real sketch on a simulated MCU -> real PGAS app code.

    python sim/run_sim.py --elf <pgas.elf> --board <pgas_board>     (see sim/README.md)

What is real here: the sketch (compiled for ATmega328P with the official
Arduino AVR core), the whole Linux-side app (pgas.board.Runtime, sessions,
job queue, the `python -m pgas.capture` CLI as a subprocess, features, ONNX
inference, agent fallback). What is simulated: the gas in the air, the
DHT22 (a timing-level protocol model), the 10k/20k dividers, a "virtual
operator" who moves the box when the app says so, and the MCU itself
(simavr instead of the UNO Q's STM32). The classifier used here is trained on
synthetic data in a temporary folder - its grades are NOT results.

Everything goes to a temporary folder; only the log is kept (sim/logs/).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix="pgas-sim-"))
os.environ["PGAS_MODELS_DIR"] = str(WORK / "models")
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from pgas import display, jobs  # noqa: E402
from pgas.board import Runtime  # noqa: E402

# Simulation parameters (module output volts). Invented for the simulation,
# not measured on real food.
CLEAN_AIR = (1.00, 0.80, 0.90)
FOODS = {
    "fresh_sim_chicken": (0.15, 0.05, 0.10),
    "swill_sim_mixed": (2.20, 1.40, 1.80),
}
TAU_RISE_S, TAU_FALL_S = 12.0, 8.0


class Log:
    def __init__(self, path: Path):
        self.fh = open(path, "w")
        self.lock = threading.Lock()

    def __call__(self, msg: str) -> None:
        line = f"{datetime.now():%H:%M:%S} {msg}"
        with self.lock:
            print(line, flush=True)
            self.fh.write(line + "\n")
            self.fh.flush()


class SimBridge:
    """Stands in for arduino.app_utils.Bridge on the Linux side."""

    def __init__(self, log: Log):
        self.log, self.frames, self.last_letter = log, 0, None

    def call(self, name, data, timeout=10):
        assert name == "draw" and len(data) == 104
        self.frames += 1
        frame = list(data)
        cells = [r * 13 + c for r in range(5) for c in range(3)]
        letter = next((ch for ch in "AMHVCTE"
                       if [frame[i] for i in cells] == [display.text3(ch)[i] for i in cells]
                       and any(frame[i] for i in cells)), None)
        icon = next((g for g in ("FRESH", "SPOILING", "DO-NOT-SELL") if frame == display.icon(g)), None)
        tag = icon or letter
        if tag and tag != self.last_letter:
            self.last_letter = tag
            self.log(f"LED matrix -> {tag}\n" + display.ascii_art(frame))


class Board:
    """The simavr process: sketch + simulated sensors."""

    def __init__(self, board_bin: str, elf: str, runtime: Runtime, log: Log):
        self.p = subprocess.Popen([board_bin, elf], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.runtime, self.log, self.samples = runtime, log, 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            line = line.strip()
            if line.startswith("S,"):
                a0, a1, a2, t, h, ok = line[2:].split(",")
                self.runtime.on_sample(int(a0), int(a1), int(a2), float(t), float(h), int(ok))
                self.samples += 1
                if self.samples % 10 == 1:
                    self.log(f"MCU -> {line}")
            elif line:
                self.log(f"MCU: {line}")

    def send(self, cmd: str):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def close(self):
        try:
            self.send("Q")
        except BrokenPipeError:
            pass
        self.p.wait(timeout=5)


class Operator(threading.Thread):
    """Virtual person + air: follows the app's prompts, sets the gas seen by the MQs."""

    def __init__(self, board: Board, jobs_dir: Path, log: Log):
        super().__init__(daemon=True)
        self.board, self.jobs_dir, self.log = board, jobs_dir, log
        self.food = (0.0, 0.0, 0.0)
        self.target, self.level, self.job = 0.0, 0.0, None
        self.seen = 0
        self.rng = random.Random(1)

    def run(self):
        dt = 0.25
        while True:
            if self.job:
                st = jobs.read_status(self.jobs_dir, self.job) or {"lines": []}
                for ln in st["lines"][self.seen:]:
                    if "MOVE NOW" in ln:
                        threading.Timer(2.0, self._set, args=(1.0, "box lowered over the food")).start()
                    elif "STEP 3/3" in ln:
                        self._set(0.0, "box lifted away from the food")
                self.seen = len(st["lines"])
            tau = TAU_RISE_S if self.target > self.level else TAU_FALL_S
            self.level += (self.target - self.level) * dt / tau
            v = [c + self.level * a + self.rng.gauss(0, 0.003) for c, a in zip(CLEAN_AIR, self.food)]
            self.board.send("G " + " ".join(f"{x:.4f}" for x in v))
            time.sleep(dt)

    def _set(self, target, what):
        self.target = target
        self.log(f"OPERATOR: {what}")

    def start_job(self, job_id, food):
        self.job, self.seen, self.food = job_id, 0, FOODS.get(food, (0, 0, 0))


def cli(args: list[str], jobs_dir: Path, log: Log) -> int:
    cmd = [sys.executable, "-m", "pgas.capture", *args, "--jobs-dir", str(jobs_dir)]
    log("$ python -m pgas.capture " + " ".join(args))
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        log(f"  | {line.rstrip()}")
    return p.wait()


def newest_job(jobs_dir: Path, after: set[str]) -> str | None:
    for _ in range(100):
        ids = {p.stem for p in (jobs_dir / "status").glob("*.json")} - after
        if ids:
            return sorted(ids)[-1]
        time.sleep(0.1)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elf", required=True)
    ap.add_argument("--board", required=True)
    ap.add_argument("--log-dir", type=Path, default=ROOT / "sim" / "logs")
    a = ap.parse_args()
    a.log_dir.mkdir(parents=True, exist_ok=True)
    log = Log(a.log_dir / f"{datetime.now():%Y%m%dT%H%M%S}_simavr_end_to_end.log")
    log("=== PGAS SIMULATION RUN - synthetic signals, NOT real measurements ===")
    log(f"work dir: {WORK}")

    from pgas import train
    from synth import make_dataset

    make_dataset(WORK / "synthetic_raw")
    card = train.run(WORK / "synthetic_raw", WORK / "models", WORK / "figs")
    log(f"placeholder classifier trained on SYNTHETIC data: {card['model']} (for plumbing only)")

    bridge = SimBridge(log)
    runtime = Runtime(bridge=bridge, data_dir=WORK / "data")
    board = Board(a.board, a.elf, runtime, log)
    board.send("E 26.5 65.0")
    op = Operator(board, runtime.jobs_dir, log)
    op.start()
    stop = threading.Event()

    def app_loop():
        while not stop.is_set():
            runtime.loop(0.2)

    threading.Thread(target=app_loop, daemon=True).start()
    time.sleep(4)  # first DHT22 read happens 2 s after reset

    results = {}
    seen: set[str] = set()
    rc = cli(["--selftest"], runtime.jobs_dir, log)
    results["selftest_exit"] = rc
    seen |= {p.stem for p in (runtime.jobs_dir / "status").glob("*.json")}

    for food in FOODS:
        th = threading.Thread(target=lambda f=food: results.__setitem__(
            f, cli(["--mode", "hood", "--label", f], runtime.jobs_dir, log)))
        th.start()
        jid = newest_job(runtime.jobs_dir, seen)
        seen.add(jid)
        op.start_job(jid, food)
        th.join()
        st = jobs.read_status(runtime.jobs_dir, jid)
        results[food] = {"exit": results[food], "state": st["state"],
                         "result": {k: v for k, v in (st["result"] or {}).items()
                                    if k in ("grade", "advice", "advice_source", "fallback_reason",
                                             "timing_s", "capture_s", "recovered", "file")}}
        op.target = 0.0

    stop.set()
    board.close()
    log(f"MCU samples received: {board.samples}, LED frames drawn: {bridge.frames}")
    log("SUMMARY (simulation, not results):\n" + json.dumps(results, indent=2))
    ok = results["selftest_exit"] == 0 and all(results[f]["state"] == "done" for f in FOODS)
    log("END-TO-END SIMULATION: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
