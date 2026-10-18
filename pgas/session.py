"""Capture sessions: hood mode and continuous mode.

Hardware-independent: a session pulls 1 Hz readings from a `Source` and shows
progress through a `Display`, so the same code runs on the board (Bridge
source + LED matrix) and in tests (mock source, no sleeping).
"""

from __future__ import annotations

import json
import math
import statistics
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from . import config, display
from .dataio import CaptureWriter, Sample


@dataclass
class Reading:
    t: float                     # wall-clock seconds (time.time()) when sampled on Linux side
    a0: float
    a1: float
    a2: float
    temp_c: float | None = None  # None when the DHT22 read failed / is stale
    rh_pct: float | None = None


class Source(Protocol):
    def read(self, timeout: float) -> Reading | None: ...
    def flush(self) -> None: ...


class Display(Protocol):
    def show(self, frame: list[int]) -> None: ...


class NullDisplay:
    def __init__(self):
        self.frames: list[list[int]] = []

    def show(self, frame: list[int]) -> None:
        self.frames.append(frame)


Log = Callable[[str], None]


class SessionError(RuntimeError):
    pass


class RetestError(SessionError):
    """A step got no usable reading; the operator should run the test again."""

    def __init__(self, step: str, reason: str):
        self.step, self.reason = step, reason
        super().__init__(f"{step}: {reason} - please re-test")


# A gas channel below 1 % of full scale means the sensor is not connected
# (a working MQ module always outputs some voltage). Readings near full scale
# are a strong smell, not a fault, so they are allowed.
MIN_GAS_FRACTION = 0.01


def _volts(raw: float) -> float:
    return config.adc_to_sensor_volts(raw)


def _next(src: Source, timeout: float = 5.0, step: str = "capture") -> Reading:
    """Next 1 Hz reading, validated; raises RetestError when it is unusable."""
    r = src.read(timeout)
    if r is None:
        raise RetestError(step, f"no sensor reading for {timeout:.0f} s (is the sketch running?)")
    floor = MIN_GAS_FRACTION * config.ADC_MAX
    for name, raw in zip(config.SENSORS, (r.a0, r.a1, r.a2)):
        if raw is None or math.isnan(raw) or raw < floor:
            pin = config.SENSOR_PINS[name]
            raise RetestError(step, f"{name.upper()} on {pin} reads {raw} - sensor not detected")
    return r


# --- Hood mode -------------------------------------------------------------

RECOVER_FRACTION = 0.10   # back to baseline: within 10 % of the exposure rise ...
RECOVER_ABS_V = 0.02      # ... plus 20 mV, on every sensor
RECOVER_HOLD = 5          # for 5 consecutive readings


@dataclass
class HoodResult:
    csv: str
    rows: int
    recovered: bool
    capture_s: float
    analysis: dict = field(default_factory=dict)


def run_hood(
    src: Source,
    disp: Display,
    out_dir: Path,
    label: str,
    log: Log = print,
    baseline_s: int = config.HOOD_BASELINE_S,
    move_s: int = 5,
    expose_s: int = config.HOOD_EXPOSE_S,
    recover_max_s: int = config.HOOD_RECOVER_MAX_S,
    meta: dict | None = None,
    stop: threading.Event | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> HoodResult:
    """`progress(phase, i, n)` is called once per second (phase: baseline,
    move, expose, recover); it is for display only and must not raise."""
    stop = stop or threading.Event()

    def tick(phase: str, i: int, n: int) -> None:
        if progress is not None:
            try:
                progress(phase, i, n)
            except Exception:  # noqa: BLE001 - display only
                pass
    src.flush()
    started = datetime.now()
    w = CaptureWriter(out_dir, "hood", label, started, meta=meta)
    log(f"recording to {w.csv_path.name}")
    t0: float | None = None
    base: dict[str, list[float]] = {s: [] for s in config.SENSORS}
    peak = {s: -math.inf for s in config.SENSORS}
    t_start = time.monotonic()

    def record(phase: str, r: Reading) -> None:
        nonlocal t0
        if t0 is None:
            t0 = r.t
        w.write(Sample(r.t - t0, phase, r.a0, r.a1, r.a2, r.temp_c, r.rh_pct))

    def vals(r: Reading) -> dict[str, float]:
        return {"mq135": _volts(r.a0), "mq3": _volts(r.a1), "mq2": _volts(r.a2)}

    try:
        log(f"STEP 1/3: hold the box in open air, away from food ({baseline_s} s)")
        for i in range(baseline_s):
            disp.show(display.countdown("A", baseline_s - i, i / baseline_s))
            tick("baseline", i, baseline_s)
            r = _next(src, step="step 1/3 (clean air)")
            record("baseline", r)
            for s, v in vals(r).items():
                base[s].append(v)
            if stop.is_set():
                raise SessionError("stopped")
        base_med = {s: statistics.median(v) for s, v in base.items()}

        log(f"MOVE NOW: put the box over the food, opening down, 3-5 cm above it ({move_s} s)")
        for i in range(move_s):
            disp.show(display.countdown("M", move_s - i, i / move_s))
            tick("move", i, move_s)
            record("move", _next(src, step="step 2/3 (move)"))

        log(f"STEP 2/3: hold the box still over the food ({expose_s} s)")
        for i in range(expose_s):
            disp.show(display.countdown("H", expose_s - i, i / expose_s))
            tick("expose", i, expose_s)
            r = _next(src, step="step 2/3 (over the food)")
            record("expose", r)
            for s, v in vals(r).items():
                peak[s] = max(peak[s], v)
            if stop.is_set():
                raise SessionError("stopped")

        log(f"STEP 3/3: lift the box away and let it air out (up to {recover_max_s} s)")
        held, recovered = 0, False
        for i in range(recover_max_s):
            disp.show(display.countdown("V", recover_max_s - i, i / recover_max_s))
            tick("recover", i, recover_max_s)
            r = _next(src, step="step 3/3 (airing out)")
            record("recover", r)
            ok = all(
                v - base_med[s] <= RECOVER_FRACTION * max(0.0, peak[s] - base_med[s]) + RECOVER_ABS_V
                for s, v in vals(r).items()
            )
            held = held + 1 if ok else 0
            if held >= RECOVER_HOLD:
                recovered = True
                break
            if stop.is_set():
                break
        log("readings back to baseline" if recovered else "recover timeout: readings not fully back to baseline")
        capture_s = time.monotonic() - t_start
        w.close(recovered=recovered, capture_s=round(capture_s, 1))
        return HoodResult(str(w.csv_path), w.rows, recovered, capture_s)
    except BaseException as e:
        w.close(error=str(e))
        raise


# --- Continuous mode -------------------------------------------------------

@dataclass
class ContinuousState:
    job_id: str
    label: str
    csv: str
    t0: float                      # wall-clock start, seconds
    until: float | None = None     # wall-clock end, or None = until stopped

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self)))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "ContinuousState | None":
        try:
            return cls(**json.loads(path.read_text()))
        except (OSError, ValueError, TypeError):
            return None


def _median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return statistics.median(xs) if xs else None


def run_continuous(
    src: Source,
    disp: Display,
    writer: CaptureWriter,
    t0: float,
    stop: threading.Event,
    until: float | None = None,
    log: Log = print,
    period_s: int = config.CONTINUOUS_PERIOD_S,
) -> int:
    """Write one row per `period_s` (median of the 1 Hz readings in that bucket).

    `t0` is the capture's wall-clock start, so a restarted app keeps appending
    to the same file with a continuous time axis.
    """
    bucket: int | None = None
    acc: dict[str, list] = {k: [] for k in ("a0", "a1", "a2", "temp_c", "rh_pct")}
    written = 0
    misses = 0

    def flush(b: int) -> None:
        nonlocal written
        if not acc["a0"]:
            return
        writer.write(Sample(
            b * period_s, "continuous",
            _median(acc["a0"]), _median(acc["a1"]), _median(acc["a2"]),
            _median(acc["temp_c"]), _median(acc["rh_pct"]),
        ))
        written += 1
        for v in acc.values():
            v.clear()

    while not stop.is_set():
        r = src.read(5.0)
        if r is None:
            misses += 1
            if misses % 12 == 1:
                log("warning: no sensor readings in the last 5 s")
            continue
        misses = 0
        if until is not None and r.t >= until:
            break
        b = int((r.t - t0) // period_s)
        if bucket is not None and b != bucket:
            flush(bucket)
            hours = (r.t - t0) / 3600
            if written % 60 == 1:
                log(f"{hours:.1f} h logged, {writer.rows} rows")
        bucket = b
        for k, v in (("a0", r.a0), ("a1", r.a1), ("a2", r.a2), ("temp_c", r.temp_c), ("rh_pct", r.rh_pct)):
            acc[k].append(v)
        hours = (r.t - t0) / 3600
        disp.show(display.countdown("C", int(hours), ((r.t - t0) % 3600) / 3600))
    if bucket is not None:
        flush(bucket)
    return written
