"""Shared constants for PGAS.

Every number here is a design parameter (wiring, protocol timing, thresholds),
not a measured result.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Wiring -----------------------------------------------------------------
# Each MQ module output goes through a 10k (top) / 20k (bottom) divider before
# reaching the UNO Q analog pin, so V_pin = V_sensor * 20 / (10 + 20).
DIVIDER_TOP_OHM = 10_000
DIVIDER_BOTTOM_OHM = 20_000
DIVIDER_RATIO = DIVIDER_BOTTOM_OHM / (DIVIDER_TOP_OHM + DIVIDER_BOTTOM_OHM)

ADC_BITS = 14          # sketch calls analogReadResolution(ADC_BITS)
ADC_MAX = (1 << ADC_BITS) - 1
ADC_VREF = 3.3         # UNO Q MCU analog reference (3.3 V logic)

# Sensor name -> analog pin. Order matters: it is the CSV column order.
SENSORS = ("mq135", "mq3", "mq2")
SENSOR_PINS = {"mq135": "A0", "mq3": "A1", "mq2": "A2"}
SENSOR_GASES = {
    "mq135": "ammonia / sulfides",
    "mq3": "ethanol",
    "mq2": "broad VOCs",
}
DHT_PIN = "D2"

# --- Protocol ----------------------------------------------------------------
SAMPLE_HZ = 1.0
HOOD_BASELINE_S = 30      # ambient air before the hood goes over the food
HOOD_EXPOSE_S = 60        # hood held 3-5 cm above the food
HOOD_RECOVER_MAX_S = 180  # vent until readings return to baseline (or timeout)
HOOD_RECOVER_TOL = 0.05   # "back to baseline": every sensor within 5 % of its
                          # baseline range-normalised value (see capture.py)
SLOPE_WINDOW_S = 20       # rise slope measured over the first 20 s of exposure

CONTINUOUS_PERIOD_S = 60  # one CSV row per minute
CONTINUOUS_BASELINE_ROWS = 10  # first 10 minutes = the "fresh" baseline

# --- Grades ------------------------------------------------------------------
GRADES = ("FRESH", "SPOILING", "DO-NOT-SELL")

# --- Agent -------------------------------------------------------------------
LLM_TIMEOUT_S = 20.0

# --- Paths -------------------------------------------------------------------
_PKG = Path(__file__).resolve().parent
REPO_ROOT = _PKG.parent


def _app_root() -> Path:
    """Root that holds data/ and models/.

    In the repository: the repo root. When deployed as an App Lab app the
    package lives in <app>/python/pgas and data/ + models/ sit next to app.yaml
    (<app> is /app inside the container, ~/ArduinoApps/pgas on the board).
    """
    if _PKG.parent.name == "python" and (_PKG.parent.parent / "app.yaml").exists():
        return _PKG.parent.parent
    return REPO_ROOT


APP_ROOT = _app_root()
DATA_DIR = APP_ROOT / "data"
DATA_RAW = DATA_DIR / "raw"
JOBS_DIR = DATA_DIR / "jobs"
MODELS_DIR = Path(os.environ.get("PGAS_MODELS_DIR") or APP_ROOT / "models")
FIGURES_DIR = REPO_ROOT / "docs" / "figures"


def adc_to_sensor_volts(raw: float) -> float:
    """Convert a raw ADC count to the MQ module output voltage (before divider)."""
    return (raw / ADC_MAX) * ADC_VREF / DIVIDER_RATIO


def adc_to_pin_volts(raw: float) -> float:
    """Convert a raw ADC count to the voltage actually present on the pin."""
    return (raw / ADC_MAX) * ADC_VREF
