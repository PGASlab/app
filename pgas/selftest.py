"""Hardware self-test.

    python -m pgas.selftest                 # on the board (asks the running app)
    python -m pgas.selftest --host pgas.local   # from the Mac over ssh

Collects ~20 s of 1 Hz readings and checks:

* Bridge      - readings arrive from the MCU at ~1 Hz
* <MQ> range  - pin voltage is above 1 % of full scale (not floating / shorted to
                GND) and below 97 % (the 10k/20k divider keeps a 5 V output at
                3.33 V, so near-full-scale means saturation or a wiring fault)
* <MQ> stable - spread over the window < 0.10 V at the sensor (heaters warmed up;
                a cold MQ drifts strongly for the first minutes)
* DHT22       - at least half the readings valid, -10..60 C and 0..100 %RH
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import config

STABLE_SPREAD_V = 0.10
MIN_FRACTION, MAX_FRACTION = 0.01, 0.97


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def evaluate(readings: list, duration_s: float) -> list[Check]:
    """`readings` are session.Reading-like objects with a0, a1, a2, temp_c, rh_pct."""
    checks: list[Check] = []
    n = len(readings)
    rate = n / duration_s if duration_s > 0 else 0.0
    checks.append(Check("Bridge (MCU -> Linux)", 0.8 <= rate <= 1.3,
                        f"{n} readings in {duration_s:.0f} s ({rate:.2f} Hz)"))
    if n == 0:
        return checks
    for s, attr in zip(config.SENSORS, ("a0", "a1", "a2")):
        raws = [getattr(r, attr) for r in readings]
        lo, hi = min(raws), max(raws)
        pin_hi = config.adc_to_pin_volts(hi)
        in_range = lo >= MIN_FRACTION * config.ADC_MAX and hi <= MAX_FRACTION * config.ADC_MAX
        checks.append(Check(
            f"{s.upper()} on {config.SENSOR_PINS[s]} range", in_range,
            f"pin {config.adc_to_pin_volts(lo):.3f}-{pin_hi:.3f} V "
            f"(sensor {config.adc_to_sensor_volts(lo):.3f}-{config.adc_to_sensor_volts(hi):.3f} V)",
        ))
        spread = config.adc_to_sensor_volts(hi) - config.adc_to_sensor_volts(lo)
        checks.append(Check(f"{s.upper()} stable", spread < STABLE_SPREAD_V,
                            f"spread {spread:.3f} V (limit {STABLE_SPREAD_V} V)"))
    good = [r for r in readings
            if r.temp_c is not None and r.rh_pct is not None
            and not math.isnan(r.temp_c) and not math.isnan(r.rh_pct)
            and -10 <= r.temp_c <= 60 and 0 <= r.rh_pct <= 100]
    if good:
        t = sum(r.temp_c for r in good) / len(good)
        h = sum(r.rh_pct for r in good) / len(good)
        detail = f"{len(good)}/{n} valid, {t:.1f} C, {h:.1f} %RH"
    else:
        detail = f"0/{n} valid readings"
    checks.append(Check(f"DHT22 on {config.DHT_PIN}", len(good) >= n / 2, detail))
    return checks


def report(checks: list[Check]) -> str:
    lines = [f"[{'PASS' if c.ok else 'FAIL'}] {c.name}: {c.detail}" for c in checks]
    overall = all(c.ok for c in checks)
    lines.append(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import sys

    from .capture import main as capture_main

    return capture_main(["--selftest", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())
