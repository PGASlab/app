"""Reading and writing PGAS capture files.

A capture is one CSV file plus a JSON sidecar with the same stem:

    data/raw/<YYYYmmddTHHMMSS>_<mode>_<label>.csv
    data/raw/<YYYYmmddTHHMMSS>_<mode>_<label>.json

CSV columns (one row per sample):

    t_s        seconds since the capture started
    phase      baseline | expose | recover (hood mode) or continuous
    mq135_raw  raw ADC count on A0
    mq3_raw    raw ADC count on A1
    mq2_raw    raw ADC count on A2
    temp_c     DHT22 temperature, empty if the read failed
    rh_pct     DHT22 relative humidity, empty if the read failed
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np

from . import config

COLUMNS = ("t_s", "phase", "mq135_raw", "mq3_raw", "mq2_raw", "temp_c", "rh_pct")
MODES = ("hood", "continuous")
_LABEL_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_STEM_RE = re.compile(r"^(?P<ts>\d{8}T\d{6})_(?P<mode>hood|continuous)_(?P<label>[a-z0-9_]+)$")


@dataclass
class Sample:
    t_s: float
    phase: str
    mq135_raw: float
    mq3_raw: float
    mq2_raw: float
    temp_c: float | None = None
    rh_pct: float | None = None

    def raw(self, sensor: str) -> float:
        return getattr(self, f"{sensor}_raw")


@dataclass
class Capture:
    """A loaded capture: arrays keyed by column plus metadata."""

    path: Path
    mode: str
    label: str
    started: datetime
    t_s: np.ndarray
    phase: np.ndarray
    raw: dict[str, np.ndarray]
    temp_c: np.ndarray
    rh_pct: np.ndarray
    meta: dict = field(default_factory=dict)

    @property
    def session_id(self) -> str:
        return self.path.stem

    def volts(self, sensor: str) -> np.ndarray:
        """MQ module output voltage (divider undone)."""
        return self.raw[sensor] / config.ADC_MAX * config.ADC_VREF / config.DIVIDER_RATIO

    def mask(self, phase: str) -> np.ndarray:
        return self.phase == phase

    def __len__(self) -> int:
        return len(self.t_s)


def validate_label(label: str) -> str:
    if not _LABEL_RE.match(label):
        raise ValueError(
            f"label {label!r} must be lowercase letters/digits separated by '_' "
            "(e.g. fresh_chicken)"
        )
    return label


def capture_stem(mode: str, label: str, started: datetime) -> str:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    validate_label(label)
    return f"{started.strftime('%Y%m%dT%H%M%S')}_{mode}_{label}"


def parse_stem(stem: str) -> tuple[datetime, str, str]:
    m = _STEM_RE.match(stem)
    if not m:
        raise ValueError(f"not a PGAS capture name: {stem}")
    return datetime.strptime(m["ts"], "%Y%m%dT%H%M%S"), m["mode"], m["label"]


def _fmt(v: float | None) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


class CaptureWriter:
    """Append-only CSV writer that flushes every row (safe for 48 h runs)."""

    def __init__(self, out_dir: Path, mode: str, label: str, started: datetime, meta: dict | None = None):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = capture_stem(mode, label, started)
        self.csv_path = out_dir / f"{stem}.csv"
        self.meta_path = out_dir / f"{stem}.json"
        self.meta = {
            "mode": mode,
            "label": label,
            "started": started.isoformat(timespec="seconds"),
            "adc_bits": config.ADC_BITS,
            "adc_vref": config.ADC_VREF,
            "divider_ratio": config.DIVIDER_RATIO,
            "sensors": {s: {"pin": config.SENSOR_PINS[s], "gas": config.SENSOR_GASES[s]} for s in config.SENSORS},
            **(meta or {}),
        }
        self._fh = open(self.csv_path, "w", newline="")
        self._w = csv.writer(self._fh)
        self._w.writerow(COLUMNS)
        self._fh.flush()
        self.rows = 0
        self.write_meta()

    def write_meta(self, **extra) -> None:
        self.meta.update(extra)
        self.meta_path.write_text(json.dumps(self.meta, indent=2) + "\n")

    def write(self, s: Sample) -> None:
        self._w.writerow([
            f"{s.t_s:.1f}", s.phase,
            _fmt(s.mq135_raw), _fmt(s.mq3_raw), _fmt(s.mq2_raw),
            _fmt(s.temp_c), _fmt(s.rh_pct),
        ])
        self._fh.flush()
        self.rows += 1

    def close(self, **extra) -> None:
        self.write_meta(rows=self.rows, **extra)
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if not self._fh.closed:
            self.close()


def _f(x: str) -> float:
    return float(x) if x not in ("", None) else math.nan


def load_capture(path: Path | str) -> Capture:
    path = Path(path)
    started, mode, label = parse_stem(path.stem)
    meta_path = path.with_suffix(".json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if rows and tuple(rows[0].keys()) != COLUMNS:
        raise ValueError(f"{path}: unexpected columns {tuple(rows[0].keys())}")
    return Capture(
        path=path,
        mode=mode,
        label=label,
        started=started,
        t_s=np.array([_f(r["t_s"]) for r in rows]),
        phase=np.array([r["phase"] for r in rows], dtype=object),
        raw={s: np.array([_f(r[f"{s}_raw"]) for r in rows]) for s in config.SENSORS},
        temp_c=np.array([_f(r["temp_c"]) for r in rows]),
        rh_pct=np.array([_f(r["rh_pct"]) for r in rows]),
        meta=meta,
    )


def list_captures(data_dir: Path | str = config.DATA_RAW, mode: str | None = None) -> list[Path]:
    paths = []
    for p in sorted(Path(data_dir).glob("*.csv")):
        try:
            _, m, _ = parse_stem(p.stem)
        except ValueError:
            continue
        if mode is None or m == mode:
            paths.append(p)
    return paths


def samples_to_capture(samples: Iterable[Sample], mode: str = "hood", label: str = "live") -> Capture:
    """Build an in-memory Capture (used for live inference without a file)."""
    samples = list(samples)
    return Capture(
        path=Path(f"{capture_stem(mode, label, datetime.now())}.csv"),
        mode=mode,
        label=label,
        started=datetime.now(),
        t_s=np.array([s.t_s for s in samples], dtype=float),
        phase=np.array([s.phase for s in samples], dtype=object),
        raw={k: np.array([s.raw(k) for s in samples], dtype=float) for k in config.SENSORS},
        temp_c=np.array([math.nan if s.temp_c is None else s.temp_c for s in samples]),
        rh_pct=np.array([math.nan if s.rh_pct is None else s.rh_pct for s in samples]),
    )
