import math

import pytest

from pgas import rules


def _f(a, b, c):
    return {"mq135_d_peak": a, "mq3_d_peak": b, "mq2_d_peak": c, "temp_c": math.nan}


@pytest.mark.parametrize("vals,grade", [
    ((0.0, 0.02, 0.05), "FRESH"),
    ((0.0, 0.10, 0.0), "SPOILING"),
    ((0.25, 0.0, 0.0), "DO-NOT-SELL"),
    ((-0.1, -0.1, -0.1), "FRESH"),
])
def test_quick_grade_uses_largest_gas_rise(vals, grade):
    g, r = rules.quick_grade(_f(*vals))
    assert g == grade and set(r) == {"mq135", "mq3", "mq2"}


def test_quick_grade_ignores_dht_but_needs_gas():
    with pytest.raises(ValueError):
        rules.quick_grade({"mq135_d_peak": 0.1, "mq3_d_peak": math.nan, "mq2_d_peak": 0.0})
