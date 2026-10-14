"""Reproducible grade labels for training data.

See docs/labeling.md for the rationale. Summary:

Continuous captures (food sitting under the box for 24-48 h)
    1. Cut the recording into windows (features.continuous_windows).
    2. For each MQ sensor take the window's d_median (volts above the fresh
       baseline), clip at 0, and divide by that sensor's largest d_median in
       the same recording. Sensors whose largest rise is below
       MIN_RISE_V are treated as uninformative and contribute 0.
    3. Spoilage index = mean of those normalised rises over the sensors (0..1).
    4. Running maximum of the index (spoilage does not reverse).
    5. index <  SPOILING_AT     -> FRESH
       index <  DO_NOT_SELL_AT  -> SPOILING
       otherwise                -> DO-NOT-SELL

Hood captures
    The label is set by the operator when capturing, through its prefix:
    fresh_*  -> FRESH,  spoiling_* -> SPOILING,
    spoiled_* / swill_* -> DO-NOT-SELL.  Anything else is not used for training.
"""

from __future__ import annotations

import numpy as np

from . import config
from .features import Window

SPOILING_AT = 0.25
DO_NOT_SELL_AT = 0.60
MIN_RISE_V = 0.05

HOOD_PREFIXES = {
    "fresh": "FRESH",
    "spoiling": "SPOILING",
    "spoiled": "DO-NOT-SELL",
    "swill": "DO-NOT-SELL",
}


def spoilage_index(windows: list[Window]) -> np.ndarray:
    if not windows:
        return np.zeros(0)
    parts = []
    for s in config.SENSORS:
        rise = np.clip(np.array([w.features[f"{s}_d_median"] for w in windows]), 0, None)
        top = rise.max()
        parts.append(rise / top if top >= MIN_RISE_V else np.zeros_like(rise))
    idx = np.mean(parts, axis=0)
    return np.maximum.accumulate(idx)


def grade_from_index(idx: float) -> str:
    if idx < SPOILING_AT:
        return "FRESH"
    if idx < DO_NOT_SELL_AT:
        return "SPOILING"
    return "DO-NOT-SELL"


def label_continuous(windows: list[Window]) -> list[str]:
    return [grade_from_index(i) for i in spoilage_index(windows)]


def label_hood(label: str) -> str | None:
    prefix = label.split("_", 1)[0]
    return HOOD_PREFIXES.get(prefix)
