"""Feature extraction.

For every MQ sensor, working in module output volts (divider undone):

    <s>_d_median  median(window)  - median(baseline)
    <s>_d_peak    max(window)     - median(baseline)
    <s>_d_mean    mean(window)    - median(baseline)
    <s>_slope20   least-squares slope (V/s) over the first 20 s of the window

plus the mean temperature (deg C) and relative humidity (%) during the window.

Hood captures: baseline = the 30 s "baseline" phase, window = the 60 s
"expose" phase.

Continuous captures: baseline = the first CONTINUOUS_BASELINE_ROWS rows, and
the rest of the recording is cut into fixed-length windows. Continuous mode
logs one row per minute, so the 20 s slope is undefined there (NaN); that is
why the classifier can be trained on the CORE feature set without slopes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import config
from .dataio import Capture

PER_SENSOR = ("d_median", "d_peak", "d_mean", "slope20")
ENV = ("temp_c", "rh_pct")

ALL_FEATURES = tuple(f"{s}_{k}" for s in config.SENSORS for k in PER_SENSOR) + ENV
CORE_FEATURES = tuple(f for f in ALL_FEATURES if not f.endswith("slope20"))
FEATURE_SETS = {"core": CORE_FEATURES, "full": ALL_FEATURES}


def _nanmean(a: np.ndarray) -> float:
    a = a[~np.isnan(a)]
    return float(a.mean()) if a.size else math.nan


def rise_slope(t: np.ndarray, v: np.ndarray, window_s: float = config.SLOPE_WINDOW_S) -> float:
    """Least-squares slope of v vs t over the first `window_s` seconds.

    Returns NaN when fewer than 3 valid points fall inside the window.
    """
    if t.size == 0:
        return math.nan
    sel = (t - t[0] <= window_s) & ~np.isnan(v)
    if sel.sum() < 3:
        return math.nan
    tt, vv = t[sel] - t[sel][0], v[sel]
    if np.ptp(tt) == 0:
        return math.nan
    return float(np.polyfit(tt, vv, 1)[0])


def window_features(
    t: np.ndarray,
    volts: dict[str, np.ndarray],
    baseline_volts: dict[str, np.ndarray],
    temp_c: np.ndarray,
    rh_pct: np.ndarray,
) -> dict[str, float]:
    """Compute the feature dict for one window against one baseline."""
    out: dict[str, float] = {}
    for s in config.SENSORS:
        base = baseline_volts[s]
        base = base[~np.isnan(base)]
        if base.size == 0:
            raise ValueError(f"empty baseline for {s}")
        b = float(np.median(base))
        w = volts[s]
        valid = w[~np.isnan(w)]
        if valid.size == 0:
            raise ValueError(f"empty window for {s}")
        out[f"{s}_d_median"] = float(np.median(valid)) - b
        out[f"{s}_d_peak"] = float(valid.max()) - b
        out[f"{s}_d_mean"] = float(valid.mean()) - b
        out[f"{s}_slope20"] = rise_slope(t, w)
    out["temp_c"] = _nanmean(temp_c)
    out["rh_pct"] = _nanmean(rh_pct)
    return out


def hood_features(cap: Capture) -> dict[str, float]:
    """Features for one hood capture (baseline phase vs expose phase)."""
    b, e = cap.mask("baseline"), cap.mask("expose")
    if not b.any() or not e.any():
        raise ValueError(f"{cap.path.name}: hood capture needs baseline and expose phases")
    volts = {s: cap.volts(s) for s in config.SENSORS}
    return window_features(
        cap.t_s[e],
        {s: v[e] for s, v in volts.items()},
        {s: v[b] for s, v in volts.items()},
        cap.temp_c[e],
        cap.rh_pct[e],
    )


@dataclass
class Window:
    session_id: str
    label: str            # capture label (food name), not the grade
    start_h: float        # window start, hours since capture start
    end_h: float
    features: dict[str, float]


def continuous_windows(
    cap: Capture,
    window_rows: int = 30,
    step_rows: int = 30,
    baseline_rows: int = config.CONTINUOUS_BASELINE_ROWS,
) -> list[Window]:
    """Cut a continuous capture into windows; all share the opening baseline."""
    n = len(cap)
    if n < baseline_rows + window_rows:
        return []
    volts = {s: cap.volts(s) for s in config.SENSORS}
    base = {s: v[:baseline_rows] for s, v in volts.items()}
    wins = []
    for start in range(baseline_rows, n - window_rows + 1, step_rows):
        sl = slice(start, start + window_rows)
        feats = window_features(
            cap.t_s[sl], {s: v[sl] for s, v in volts.items()}, base, cap.temp_c[sl], cap.rh_pct[sl]
        )
        wins.append(Window(cap.session_id, cap.label, cap.t_s[start] / 3600, cap.t_s[sl][-1] / 3600, feats))
    return wins


def vector(features: dict[str, float], names: tuple[str, ...] = CORE_FEATURES) -> np.ndarray:
    return np.array([features[n] for n in names], dtype=np.float32)
