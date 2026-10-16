# Simulating PGAS

No simulator supports the Arduino UNO Q (STM32U585 + Linux + Bridge). PGAS
therefore runs the same sketch on an **Arduino Uno R3 stand-in**. When it is
compiled for AVR, `app/sketch/sketch.ino` swaps the Bridge and LED matrix for
`Serial` and converts the Uno's 10-bit / 5 V readings to the UNO Q scale
(14-bit / 3.3 V). The sampling loop, the averaging and the DHT22 driver are the
same code that runs on the UNO Q.

Nothing produced by a simulation is a result. Simulation captures are written to
a temporary folder, never to `data/raw/`.

## 0. In the browser, offline: `sim/web/pgas-circuit-sim.html`

Open the file in any browser (double-click; no server or internet needed). It
runs the **real firmware** (`pgas.hex` built from `app/sketch/sketch.ino`)
instruction by instruction in [avr8js](https://github.com/wokwi/avr8js), the
open-source AVR emulator that Wokwi is built on, inside the PGAS wiring:

- sliders for each MQ module output, with the 10k/20k divider voltages shown live on the diagram;
- a DHT22 protocol model on D2 (the wire flashes on every read);
- the serial monitor;
- a hood-mode run on an 8 × 13 LED matrix.

The hood panel is a browser port of `pgas/session.py` and `pgas/display.py`.
The Python originals are what the board runs, and they are exercised by the
simavr run below. Rebuild after changing the sketch:
`sim/build_avr.sh <ArduinoCore-avr> build/sim && sim/web/build.sh build/sim/pgas.hex`.

## 1. In the browser: Wokwi (free, no install)

1. Open <https://wokwi.com/projects/new/arduino-uno>. You don't need to log in to run it.
2. In the **sketch.ino** tab, replace everything with the contents of
   [`app/sketch/sketch.ino`](../app/sketch/sketch.ino).
3. In the **diagram.json** tab, replace everything with
   [`sim/wokwi/diagram.json`](wokwi/diagram.json).
4. Press ▶ Start. The Serial Monitor prints one line per second:
   `S,<a0>,<a1>,<a2>,<temp_c>,<rh_pct>,<dht_ok>`.

What the parts stand for:

| Wokwi part | Real part | Note |
|---|---|---|
| slide potentiometer `mq135` → A0 | MQ-135 output **after** the 10k/20k divider | Wokwi can't simulate a resistor divider feeding an analog input (see the caution on the [wokwi-resistor page](https://docs.wokwi.com/parts/wokwi-resistor)), so the slider is the divider's output. Keep it below 66 % (3.3 V) to stay within the range the real divider can produce. |
| slide potentiometer `mq3` → A1 | MQ-3 after its divider | same |
| slide potentiometer `mq2` → A2 | MQ-2 after its divider | same |
| `dht` (DHT22) → D2 + 10 kΩ pull-up to 3.3 V | DHT22 / AM2302 | Click it to change temperature and humidity. |

Move a slider: the matching column jumps on the next line. That is what the
sketch sends to Linux when gas reaches the sensor. The `dht_ok` column turns 1
about 2 s after start.

The Wokwi VS Code extension also works. Build the firmware first
(`sim/build_avr.sh`, below), then open `sim/wokwi/`; `wokwi.toml` points to
`build/sim/pgas.hex`.

## 2. Full system, locally or in CI: simavr

This runs the **real sketch** on a simulated ATmega328P with:

- the 10k/20k dividers computed in the harness;
- a timing-level DHT22 model (start pulse, 80/80 µs response, 40 bits, checksum);
- the **real Linux-side app**: `pgas.board.Runtime`, the job queue, the
  `python -m pgas.capture` CLI, features, ONNX inference and the agent fallback.

A "virtual operator" follows the app's prompts (A → M → H → V) and moves a
simulated box over simulated food.

```bash
# Ubuntu (CI does exactly this):
sudo apt install gcc-avr avr-libc simavr libsimavr-dev libelf-dev
# macOS: brew tap osx-cross/avr && brew install avr-gcc simavr

git clone --depth 1 https://github.com/arduino/ArduinoCore-avr build/ArduinoCore-avr
sim/build_avr.sh build/ArduinoCore-avr build/sim      # sketch -> build/sim/pgas.elf
sim/build_board.sh build/sim                           # virtual board -> build/sim/pgas_board

PGAS_SIM_ELF=build/sim/pgas.elf PGAS_SIM_BOARD=build/sim/pgas_board .venv/bin/python -m pytest tests/test_sim.py
.venv/bin/python sim/run_sim.py --elf build/sim/pgas.elf --board build/sim/pgas_board
```

The end-to-end run does a self-test, then a hood capture over "fresh chicken" and
one over "swill". The log goes to `sim/logs/`. The classifier in this run is
trained on **synthetic** data in a temporary folder, only to exercise the
pipeline. The grades it prints say nothing about real food.

## What the simulation does *not* cover

- The UNO Q's own toolchain (Zephyr core), the Bridge/router and the LED matrix
  hardware. These are only verified on the real board, the first time
  `scripts/deploy.sh` compiles and starts the app.
- Real MQ sensor behaviour (warm-up drift, humidity cross-sensitivity, how
  specific each sensor is to each gas).
- The Gemma LLM. With no model in the simulation, the rule-based fallback is used.
