"""Synthetic captures for TESTS ONLY.

Every file written here is marked "synthetic": true in its JSON sidecar, and
pgas.train / pgas.plot refuse to publish anything built from such files inside
the repository. None of these numbers describe real food.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from pgas import config
from pgas.dataio import CaptureWriter, Sample

BASE_RAW = {"mq135": 3000.0, "mq3": 2500.0, "mq2": 2800.0}


def write_hood(out: Path, label: str, rise_raw: float, started: datetime, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    w = CaptureWriter(out, "hood", label, started, meta={"synthetic": True})
    t = 0.0
    for phase, n in (("baseline", config.HOOD_BASELINE_S), ("expose", config.HOOD_EXPOSE_S), ("recover", 30)):
        for i in range(n):
            if phase == "expose":
                k = 1 - np.exp(-i / 15)
            elif phase == "recover":
                k = np.exp(-i / 10)
            else:
                k = 0.0
            vals = {s: BASE_RAW[s] + rise_raw * k * (1 + 0.3 * j) + rng.normal(0, 5)
                    for j, s in enumerate(config.SENSORS)}
            w.write(Sample(t, phase, vals["mq135"], vals["mq3"], vals["mq2"], 27.0, 70.0))
            t += 1.0
    w.close()
    return w.csv_path


def write_continuous(out: Path, label: str, hours: float, started: datetime, seed: int = 0,
                     drop_dht_every: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    w = CaptureWriter(out, "continuous", label, started, meta={"synthetic": True})
    n = int(hours * 60)
    for i in range(n):
        h = i / 60
        k = 1 / (1 + np.exp(-(h - hours / 2) / (hours / 10)))  # sigmoid rise
        vals = {s: BASE_RAW[s] + 2000 * k * (1 + 0.2 * j) + rng.normal(0, 5)
                for j, s in enumerate(config.SENSORS)}
        dht_ok = not (drop_dht_every and i % drop_dht_every == 0)
        w.write(Sample(i * 60.0, "continuous", vals["mq135"], vals["mq3"], vals["mq2"],
                       27.0 if dht_ok else None, 70.0 if dht_ok else None))
    w.close()
    return w.csv_path


def make_dataset(out: Path) -> list[Path]:
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    paths = []
    for i in range(3):
        paths.append(write_hood(out, "fresh_chicken", 50, t0 + timedelta(minutes=i), seed=i))
        paths.append(write_hood(out, "swill_mixed", 1500, t0 + timedelta(minutes=10 + i), seed=10 + i))
    paths.append(write_continuous(out, "chicken_room_temp", 12, t0 + timedelta(hours=1), seed=20))
    paths.append(write_continuous(out, "tofu_room_temp", 12, t0 + timedelta(hours=2), seed=21))
    return paths
