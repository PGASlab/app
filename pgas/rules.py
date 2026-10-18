"""Rule-based grade from one hood capture, used until a classifier is trained.

The rule looks only at the three MQ gas sensors (the DHT22 is ignored): how
far each sensor's voltage rose above its clean-air baseline while the box was
over the food (`<sensor>_d_peak`, volts at the module output).

    largest rise >= SPOILED_RISE_V   -> DO-NOT-SELL
    largest rise >= SPOILING_RISE_V  -> SPOILING
    otherwise                        -> FRESH

The two thresholds are provisional design parameters, not measured results.
Tune them once fresh and spoiled captures of the same food are compared, then
replace this rule with the trained classifier (python -m pgas.train).
"""

from __future__ import annotations

import math

from . import config

SPOILING_RISE_V = 0.10
SPOILED_RISE_V = 0.20


def rises(features: dict[str, float]) -> dict[str, float]:
    out = {}
    for s in config.SENSORS:
        v = features.get(f"{s}_d_peak")
        if v is None or (isinstance(v, float) and math.isnan(v)):
            raise ValueError(f"missing {s}_d_peak")
        out[s] = float(v)
    return out


def quick_grade(features: dict[str, float]) -> tuple[str, dict[str, float]]:
    r = rises(features)
    top = max(r.values())
    if top >= SPOILED_RISE_V:
        grade = "DO-NOT-SELL"
    elif top >= SPOILING_RISE_V:
        grade = "SPOILING"
    else:
        grade = "FRESH"
    return grade, {k: round(v, 3) for k, v in r.items()}
