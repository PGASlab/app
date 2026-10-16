"""Simulation checks.

* diagram.json uses only parts/pins that exist in Wokwi (pin names taken from
  wokwi-elements) and matches the real wiring (A0/A1/A2/D2, 10k pull-up).
* If PGAS_SIM_ELF and PGAS_SIM_BOARD point to a built firmware + simavr board
  (CI builds them), run the real sketch for a few seconds and check the
  divider maths, the 14-bit conversion and the DHT22 driver.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from pgas import config

PINS = {
    "wokwi-arduino-uno": {"A0", "A1", "A2", "A3", "A4", "A5", "AREF", "IOREF", "RESET", "VIN", "3.3V", "5V",
                          "GND.1", "GND.2", "GND.3", "A4.2", "A5.2", *map(str, range(14))},
    "wokwi-slide-potentiometer": {"VCC", "SIG", "GND"},
    "wokwi-dht22": {"VCC", "SDA", "NC", "GND"},
    "wokwi-resistor": {"1", "2"},
}
DIAGRAM = config.REPO_ROOT / "sim" / "wokwi" / "diagram.json"


def test_wokwi_diagram_valid():
    d = json.loads(DIAGRAM.read_text())
    types = {p["id"]: p["type"] for p in d["parts"]}
    for a, b, *_ in d["connections"]:
        for end in (a, b):
            pid, pin = end.split(":", 1)
            assert pid in types, end
            assert pin in PINS[types[pid]], end
    conns = {tuple(sorted(c[:2])) for c in d["connections"]}
    assert tuple(sorted(("mq135:SIG", "uno:A0"))) in conns
    assert tuple(sorted(("mq3:SIG", "uno:A1"))) in conns
    assert tuple(sorted(("mq2:SIG", "uno:A2"))) in conns
    assert tuple(sorted(("dht:SDA", "uno:2"))) in conns
    pull = next(p for p in d["parts"] if p["id"] == "r_pullup")
    assert pull["attrs"]["value"] == "10000"
    assert tuple(sorted(("r_pullup:1", "uno:3.3V"))) in conns


ELF, BOARD = os.environ.get("PGAS_SIM_ELF"), os.environ.get("PGAS_SIM_BOARD")


@pytest.mark.skipif(not (ELF and BOARD), reason="set PGAS_SIM_ELF / PGAS_SIM_BOARD (see sim/README.md)")
def test_sketch_on_simavr():
    p = subprocess.Popen([BOARD, ELF], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    p.stdin.write("G 1.2 0.9 1.0\nE 27.3 64.8\n")
    p.stdin.flush()
    time.sleep(5.5)
    p.stdin.write("Q\n")
    p.stdin.flush()
    out = p.communicate(timeout=10)[0]
    rows = [ln[2:].split(",") for ln in out.splitlines() if ln.startswith("S,")]
    assert len(rows) >= 4, out
    last = rows[-1]
    for raw, module_v in zip(last[:3], (1.2, 0.9, 1.0)):
        expect = module_v * config.DIVIDER_RATIO / config.ADC_VREF * config.ADC_MAX
        assert abs(int(raw) - expect) < 40  # Uno 10-bit quantisation ~ 25 counts
        assert abs(config.adc_to_sensor_volts(int(raw)) - module_v) < 0.02
    assert last[3:] == ["27.3", "64.8", "1"], last
