---
title: "PGAS: an AI nose on the Arduino UNO Q that tells you when food has gone bad"
published: false
tags: arduino, iot, ai, devchallenge
cover_image: "[COVER_IMAGE_URL]"
---

*Submission for the **Best Use of Arduino** prize: a physical agent that senses and acts, built on the Arduino UNO Q.*

## The modern silver spoon

For centuries people tested food with a silver spoon, because silver turns black
when it meets the sulfides that spoiling food gives off. PGAS does the same job
with three gas sensors and an Arduino UNO Q. It smells the food, decides on the
board whether it is fine or has gone bad, and then acts: the LED matrix on the
board flashes a warning and an alert goes out.

We built it for night-market stalls and small food businesses. Selling spoiled
food is a health risk, and throwing away food that is still good is waste. PGAS
runs entirely on the board. It needs no cloud, no account and no internet once
it is set up.

▶ **Demo video:** [VIDEO_URL]
▶ **Try it without hardware:** [live UNO Q simulation](https://claude.ai/artifact/BoE3spE76moKDwF9TGCZLH)
▶ **Code (MIT):** [github.com/PGASlab/app](https://github.com/PGASlab/app)

## What it does

1. Put the food in a small zip bag.
2. Open the PGAS page on your phone (the board serves it over Wi-Fi) and press **Start test**.
3. The page walks you through the three sensors, one at a time, 5 seconds each:
   hold the sensor in clean air, put it in the bag, keep it still while it measures.
4. A pop-up says **Food looks fine** or **Food has gone bad**, and the board's
   LED matrix shows ✓ or flashes ✕.

![Dashboard during a test]([SCREENSHOT_TEST_URL])
![Result pop-up]([SCREENSHOT_RESULT_URL])

## Sense → decide → act

PGAS is a small physical agent. Every test runs one loop on the UNO Q:

| Step | What happens | Where |
|---|---|---|
| **Sense** | MQ-135 (ammonia, sulfides), MQ-3 (ethanol) and MQ-2 (broad VOCs) are read at 1 Hz with the 14-bit ADC, averaged 16× | STM32U585 MCU (Arduino sketch) |
| **Decide** | For each sensor: rise in the bag over its own clean-air reading. The largest rise sets the verdict (≥ 0.10 V spoiling, ≥ 0.20 V spoiled) | QRB2210 Linux side (Python, App Lab app) |
| **Act** | LED matrix flashes ✕ three times for spoiled food (✓ when fine), an alert is sent, and the phone shows the verdict with each sensor's rise | MCU + Linux |

The two halves of the UNO Q talk over the Arduino **Bridge**: the sketch calls
`Bridge.notify("pgas_sample", …)` once a second, and Linux sends LED-matrix
frames back with `Bridge.call("draw", …)`. The dashboard is served by the
official App Lab `arduino:web_ui` brick, so the phone only needs to be on the
same Wi-Fi or hotspot as the board.

The thresholds are a provisional rule, stated as such on the result screen. The
repo also contains the next step: a scikit-learn classifier exported to ONNX
that runs on the board (`pgas/train.py`, `pgas/infer.py`), trained on labelled
captures, plus a script for Qualcomm AI Hub (`pgas/aihub.py`). It is not trained
yet because we do not have enough labelled data. [UPDATE IF TRAINED]

## Hardware

| Part | UNO Q pin | Notes |
|---|---|---|
| MQ-135 | A0 | AO through a 10 kΩ / 20 kΩ divider (5 V → 3.33 V max at the pin) |
| MQ-3 (Waveshare) | A1 | same divider |
| MQ-2 | A2 | same divider |
| Heaters | 5 V | all grounds common |
| Power | USB-C | power bank for portable use |

The UNO Q's analog pins are not 5 V tolerant, so each MQ output goes through a
divider. The design never puts more than 3.3 V on a pin.

![Wiring]([WIRING_IMAGE_URL])

## What we measured

These are real readings from our board. We did not run a formal accuracy study.

- **Self-test after warm-up** (20 readings, 0.97 Hz over the Bridge, module output):
  MQ-135 0.87–0.88 V, MQ-3 0.45–0.47 V, MQ-2 0.94–0.96 V, all stable within 0.02 V.
- **Spoiled milk** (read from the live dashboard chart, so approximate):
  every sensor rose clearly above clean air. MQ-135 went from about 0.40 V to
  about 0.78 V, MQ-3 from about 0.31 V to about 0.72 V and MQ-2 from about
  0.68 V to about 0.97 V, then fell back once the sensor came out of the bag.
- **Fresh vs spoiled with the guided test:** [RESULT_TABLE_TBD, the three rises
  for a fresh sample and a spoiled sample from the result pop-up]

## What we learned bringing it up on real hardware

The simulation (an emulated UNO Q MCU API compiled to WebAssembly) got the logic
right, but the real board taught us more:

- **Sketch libraries.** The Bridge library needs MsgPack, DebugLog, ArxContainer
  and ArxTypeTraits listed in `sketch.yaml`. We copied the exact versions from
  an App Lab example on the board.
- **No LLM brick on our App Lab version.** `arduino-app-cli brick list` showed
  no `arduino:llm`, so the advice falls back to rule-based sentences. The code
  for on-board Gemma is there for when the brick is available.
- **`adb shell` sets an Android `TMPDIR`** that does not exist on the UNO Q, which
  broke `arduino-app-cli`. The deploy script now resets it.
- **Sensors read lower than datasheets suggest.** Our MQ-3 sat at about 0.06 V in
  clean air on a power bank. Our "sensor unplugged" check was too strict and
  rejected it, so we lowered the floor to 0.25 % of full scale.
- **One faulty part can reset the whole board.** The board rebooted every two
  minutes. `journalctl` showed each boot's log simply stopping, with no
  shutdown and no error, which points to a sudden power cut rather than a
  crash. The resets stopped when we unplugged the DHT22, and we later found its
  ground rail was not connected to the board's ground. The freshness verdict
  never depended on it, so PGAS now runs without it.
- **UX matters even for a sensor project.** Our first test took 4 minutes with
  a hood over the food. With a small bag, one sensor at a time and 5 seconds
  each, it now takes about 15 seconds plus sensor swaps.

## Why it fits "Best Use of Arduino"

- It is a **physical agent that senses and acts**: gas sensors in, LED matrix
  alarm and alert out, with the decision made on the board.
- It uses what makes the UNO Q different: the MCU and Linux working together
  over the Bridge, the built-in LED matrix, and App Lab bricks for the web UI.
- It runs **offline** on a power bank, so it can work at a market stall.

## Limits

- The verdict comes from a provisional rule, not from a trained model, and has
  only been tried on a few foods.
- MQ sensors drift with temperature and humidity and need several minutes of
  warm-up.
- This is a reference tool, not a food-safety certification. If in doubt, do
  not eat it and ask a professional.

## Team

- [@k66inthesky](https://github.com/k66inthesky)
- Built with [Claude Code](https://claude.ai/code) as AI pair programmer
