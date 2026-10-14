import math
from datetime import datetime

import numpy as np
import pytest

from pgas import config, labeling
from pgas.dataio import load_capture
from pgas.features import ALL_FEATURES, CORE_FEATURES, continuous_windows, hood_features, rise_slope, window_features
from synth import write_continuous, write_hood


def test_rise_slope_linear():
    t = np.arange(0, 60, 1.0)
    v = 0.01 * t + 1.0
    assert rise_slope(t, v) == pytest.approx(0.01)


def test_rise_slope_uses_only_first_20s():
    t = np.arange(0, 60, 1.0)
    v = np.where(t <= 20, 0.02 * t, 0.4)
    assert rise_slope(t, v) == pytest.approx(0.02)


def test_rise_slope_nan_when_too_few_points():
    assert math.isnan(rise_slope(np.array([0.0, 60.0]), np.array([1.0, 2.0])))


def test_window_features_values():
    t = np.arange(5.0)
    win = {s: np.array([1.0, 2.0, 3.0, 4.0, 10.0]) for s in config.SENSORS}
    base = {s: np.array([1.0, 1.0, 1.0]) for s in config.SENSORS}
    f = window_features(t, win, base, np.array([25.0, np.nan]), np.array([60.0, 62.0]))
    assert f["mq135_d_median"] == pytest.approx(2.0)
    assert f["mq3_d_peak"] == pytest.approx(9.0)
    assert f["mq2_d_mean"] == pytest.approx(3.0)
    assert f["temp_c"] == pytest.approx(25.0)
    assert f["rh_pct"] == pytest.approx(61.0)
    assert set(f) == set(ALL_FEATURES)


def test_hood_features_detects_rise(tmp_path):
    fresh = load_capture(write_hood(tmp_path, "fresh_x", 50, datetime(2026, 1, 1, 1)))
    bad = load_capture(write_hood(tmp_path, "swill_x", 1500, datetime(2026, 1, 1, 2)))
    ff, fb = hood_features(fresh), hood_features(bad)
    for s in config.SENSORS:
        assert fb[f"{s}_d_peak"] > ff[f"{s}_d_peak"] > 0
        assert fb[f"{s}_slope20"] > 0
    assert not any(math.isnan(ff[k]) for k in ALL_FEATURES)


def test_hood_features_requires_phases(tmp_path):
    cap = load_capture(write_continuous(tmp_path, "x", 1, datetime(2026, 1, 1)))
    with pytest.raises(ValueError):
        hood_features(cap)


def test_continuous_windows_and_labels(tmp_path):
    cap = load_capture(write_continuous(tmp_path, "chicken_room_temp", 12, datetime(2026, 1, 1)))
    wins = continuous_windows(cap, window_rows=30, step_rows=30)
    assert len(wins) == (12 * 60 - config.CONTINUOUS_BASELINE_ROWS) // 30
    assert all(math.isnan(w.features["mq135_slope20"]) for w in wins)  # 1 row/min
    assert not any(math.isnan(w.features[k]) for w in wins for k in CORE_FEATURES)
    grades = labeling.label_continuous(wins)
    assert grades[0] == "FRESH" and grades[-1] == "DO-NOT-SELL"
    order = [config.GRADES.index(g) for g in grades]
    assert order == sorted(order)  # monotonic


def test_continuous_handles_dht_dropouts(tmp_path):
    cap = load_capture(write_continuous(tmp_path, "x", 2, datetime(2026, 1, 1), drop_dht_every=3))
    wins = continuous_windows(cap)
    assert wins and all(w.features["temp_c"] == pytest.approx(27.0) for w in wins)


def test_flat_sensor_does_not_count():
    from pgas.features import Window
    feats = lambda d: {f"{s}_d_median": (d if s == "mq135" else 0.001) for s in config.SENSORS}
    wins = [Window("s", "x", i, i + 1, feats(d)) for i, d in enumerate([0, 0.2, 0.5, 1.0])]
    idx = labeling.spoilage_index(wins)
    assert idx[-1] == pytest.approx(1 / 3)


def test_label_hood():
    assert labeling.label_hood("fresh_chicken") == "FRESH"
    assert labeling.label_hood("swill_mixed") == "DO-NOT-SELL"
    assert labeling.label_hood("spoiled_tofu") == "DO-NOT-SELL"
    assert labeling.label_hood("spoiling_pork") == "SPOILING"
    assert labeling.label_hood("chicken") is None
