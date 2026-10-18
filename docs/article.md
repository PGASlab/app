---
title: "LLMs Have No Nose, So We Built One: an AI Nose on the Arduino UNO Q"
published: false
tags: devchallenge, hf26challenge, arduino, ai
cover_image: "https://raw.githubusercontent.com/PGASlab/app/main/docs/images/00-hero.jpg"
---

![LLMs have no nose. What if we built one?](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/00-hero.jpg)

*This is a submission for the [Hacktoberfest Open-Source AI Challenge: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12).*

▶ **Demo video (3:11):** [youtu.be/n88pRiuib3U](https://youtu.be/n88pRiuib3U)
▶ **Code (MIT):** [github.com/PGASlab/app](https://github.com/PGASlab/app)
▶ **Try it without hardware:** [live UNO Q simulation](https://pgaslab.github.io/pgas-sim/)

## What I Built

### LLMs have no nose

AI can read, write, see and listen. Ask a chatbot whether the milk in your
fridge has gone off, though, and the honest answer is *"I can't tell, I can't
smell it."* Smell is the one sense we use every day to keep ourselves safe from
bad food, and AI simply doesn't have it.

So we built one.

### Every sensor is a small nose

![Every sensor is a small nose: MQ-135, MQ-3 and MQ-2](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/00-small-noses.jpg)

A nose works because different receptors respond to different molecules. PGAS
copies the idea with three cheap metal-oxide gas sensors, each tuned to a
different family of spoilage gases:

- **MQ-135** smells ammonia and sulfides, the "rotten egg" end of spoilage.
- **MQ-3** smells ethanol, which bacteria and yeasts make as food ferments.
- **MQ-2** smells a broad range of volatile organic compounds.

On their own, each is just a resistor that changes with the air around it.

### Together, they make one big nose

![Together, they make one big nose](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/00-big-nose.jpg)

Wired to an **Arduino UNO Q**, the three small noses become one. The UNO Q's
microcontroller samples all three every second. Its Linux side compares them
with clean air, decides whether the food is fine, and then **acts**: the LED
matrix on the board flashes a warning, an alert goes out, and your phone shows
the verdict. No cloud, no account, no internet. It all happens on a board that
runs from a power bank.

People once tested food with a silver spoon, because silver turns black when it
meets the sulfides of rotting food. PGAS is the modern silver spoon. We built it
for night-market stalls and small food businesses, where selling spoiled food
is a health risk and throwing away good food is waste.

**The side hustle.** Many night-market stalls in Taiwan are side hustles: one
person cooking after a day job, buying ingredients in the morning and selling
until late. There is no food lab, only a nose and a guess about whether the
milk for tonight's tea or yesterday's leftovers are still safe. One bad batch
can cost a small seller their customers. PGAS is a pocket-sized second opinion
they can carry to the stall, and it runs from the same power bank as their
phone.

## Demo

{% embed https://youtu.be/n88pRiuib3U %}

Here is one real test, photo by photo, on a bottle of milk that had gone bad.

### 1. The parts

![All parts: Arduino UNO Q, breadboard, wires, power bank and three gas sensors](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/01-materials.jpg)

Everything PGAS needs:

- **Arduino UNO Q** (bottom right): an STM32U585 microcontroller and a Qualcomm
  QRB2210 running Debian Linux on one board, with a built-in 8×13 LED matrix.
- **Three gas sensors:** MQ-135 for ammonia and sulfides, MQ-3 (the orange one)
  for ethanol, MQ-2 for broad volatile compounds.
- **A breadboard** with a 10 kΩ / 20 kΩ voltage divider for each sensor, because
  the UNO Q's analog pins take at most 3.3 V and the sensors output up to 5 V.
- **A USB-C power bank.** No laptop is connected.
- **A phone** on the same Wi-Fi. The board itself serves the PGAS page.

### 2. Control test: no food nearby

![Clean-air test: "Food looks fine"](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/02-clean-air-fresh.jpg)

First we ran the full test with no food anywhere near the sensors, to make sure
PGAS does not raise false alarms. All three sensors stayed at their clean-air
level (rises of +0.03 V, +0.02 V and +0.00 V), and the board decided
**FRESH** in 0.6 ms. The LED matrix showed ✓.

### 3. The suspect: a bottle of milk past its best

![The spoiled milk bottle](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/03-spoiled-milk.jpg)

![Milk still inside the bottle](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/04-milk-inside.jpg)

Our test sample is a bottle of fresh milk that had been left to spoil. The
second photo shows there really is milk inside. We poured some into a small
container so one sensor at a time fits over it.

### 4. The guided test, one sensor at a time

Press **Start test** on the phone and the page walks you through it. Each sensor
gets 5 seconds: 1 s in clean air, 1 s to move it over the food, 3 s measuring.
A big countdown ring and the live reading show what is happening.

![Testing MQ-135 over the milk, countdown at 3](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/05-test-mq135.jpg)

**MQ-135 first.** The sensor sits over the milk while the ring counts down.

![MQ-135 and MQ-3 done, prompt to swap to MQ-2](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/06-swap-to-mq3.jpg)

**Then MQ-3.** When a sensor is done, the page tells you to take it out and get
the next one ready. Here MQ-135 and MQ-3 are ticked and MQ-2 is next.

![Pressing "Ready – test MQ-2"](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/07-press-next.jpg)

**Press the button** when the next sensor is in clean air. PGAS never moves on
by itself, so you are never rushed.

![Testing MQ-2 over the milk, countdown at 2](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/08-test-mq2.jpg)

**MQ-2 last.**

### 5. The verdict: do not eat, do not sell

![Result: "Food has gone bad", MQ-3 +0.21 V](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/09-result-do-not-sell.jpg)

PGAS says **Food has gone bad**. The MQ-3 (ethanol) rose **+0.21 V** above its
own clean-air reading, past the 0.20 V limit, so the board graded the milk
**DO-NOT-SELL** in 0.2 ms. MQ-135 rose +0.02 V and MQ-2 +0.05 V. Ethanol is what
bacteria and yeasts produce as milk ferments, so MQ-3 is the sensor we expected
to react most.

The pop-up is written for anyone: one big verdict and one bar per sensor. It
also lists what the agent did:

- **Sense:** 3 gas sensors, rise above clean air
- **Decide:** DO-NOT-SELL on the UNO Q, offline, in 0.2 ms
- **Act:** LED matrix alarm (flashing ✕), alert queued (Telegram not set up yet)

### 6. For the curious: the live gauges

Scroll down the same page and every sensor has a speedometer dial, its voltage,
its normal range and a live chart. Over the limit, the card turns red and
blinks.

![MQ-3 in clean air: 0.37 V](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/10-mq3-clean-air.jpg)

**MQ-3 in clean air: 0.37 V**, inside its normal range.

![MQ-3 over the spoiled milk: 0.70 V, card red](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/11-mq3-near-milk.jpg)

**MQ-3 held over the spoiled milk: 0.70 V.** That is almost double, and the card
turns red.

![MQ-3 30 seconds after leaving the milk: 0.38 V](https://raw.githubusercontent.com/PGASlab/app/main/docs/images/12-mq3-30s-after.jpg)

**30 seconds after taking it away: 0.38 V**, back to its clean-air value. The
sensor recovers quickly, so you can test the next food straight away.

| MQ-3 | Clean air | Over spoiled milk | 30 s later |
|---|---|---|---|
| Module output | 0.37 V | **0.70 V** | 0.38 V |

## Code

▶ [github.com/PGASlab/app](https://github.com/PGASlab/app) (MIT): the Arduino sketch, the Linux app, the phone dashboard, tests that run in CI, and a browser simulation of the UNO Q.

## How I Built It

### How it works: sense → decide → act

| Step | What happens | Where |
|---|---|---|
| **Sense** | MQ-135, MQ-3 and MQ-2 are read at 1 Hz with the 14-bit ADC, averaged 16× | STM32U585 MCU (Arduino sketch) |
| **Decide** | For each sensor: rise over its own clean-air reading. An ONNX model turns the three rises into P(spoiled), checked by a safety rule | QRB2210 Linux (Python, ONNX Runtime) |
| **Act** | LED matrix ✓ or flashing ✕, alert, verdict on the phone | MCU + Linux |

The two halves of the UNO Q talk over the Arduino **Bridge**: the sketch calls
`Bridge.notify("pgas_sample", …)` once a second, and Linux sends LED-matrix
frames back with `Bridge.call("draw", …)`. The phone page is served by the
official App Lab `arduino:web_ui` brick over Socket.IO, so the phone only needs
to be on the same Wi-Fi or hotspot.

Comparing each sensor with **its own** clean-air reading taken seconds earlier
is what makes a 5-second test work. MQ sensors drift with temperature, humidity
and warm-up, so absolute thresholds are unreliable, but a rise within a few
seconds is not.

### The open-source AI: a model that runs on the board

The verdict now comes from a small machine-learning model that runs **on the
UNO Q itself**, with no cloud:

- **Model:** logistic regression in **scikit-learn**, exported to **ONNX** and
  run by **ONNX Runtime** on the board's Linux side
  ([`pgas/bag_model.py`](https://github.com/PGASlab/app/blob/main/pgas/bag_model.py)).
  The model file is 411 bytes.
- **Input:** the three rises (MQ-135, MQ-3, MQ-2). **Output:** the probability
  that the food is spoiled. Above 80% it is DO-NOT-SELL, between 50% and 80%
  it is SPOILING.
- **Training data:** our own real measurements: the clean-air control (photo 2),
  the spoiled milk in the guided test (photo 9) and an earlier spoiled-milk test.
  Each one is repeated with ±0.01 V of noise, the spread we measured on a
  sensor at rest.
- **Safety net:** three samples is a start, not a validated model. So the board
  also runs the simple rule (largest rise ≥ 0.10 V SPOILING, ≥ 0.20 V
  DO-NOT-SELL) and keeps whichever verdict is **more severe**. A food-safety
  tool should never be talked out of a warning by a model that has seen three
  examples.

The verdicts in photos 2 and 9 were made by the rule; we trained the model from
those same tests afterwards, and it gives the same answers (7% spoiled for the
clean air, 93% for the milk). Every new labelled test makes it better:
add the rises to `SAMPLES` and run `python -m pgas.bag_model`. The repo also has
a script to optimize models for the UNO Q with Qualcomm AI Hub (`pgas/aihub.py`).

### Hardware

| Part | UNO Q pin | Notes |
|---|---|---|
| MQ-135 | A0 | AO through a 10 kΩ / 20 kΩ divider (5 V → 3.33 V max at the pin) |
| MQ-3 (Waveshare) | A1 | same divider |
| MQ-2 | A2 | same divider |
| Heaters | 5 V | all grounds common |
| Power | USB-C | 5 V power bank for portable use |

### What we learned on real hardware

The browser simulation got the logic right, but the real board taught us more:

- **Sketch libraries.** The Bridge library needs MsgPack, DebugLog, ArxContainer
  and ArxTypeTraits listed in `sketch.yaml`. We copied the exact versions from
  an App Lab example on the board.
- **No LLM brick on our App Lab version**, so the advice text is rule-based.
- **`adb shell` sets an Android `TMPDIR`** that does not exist on the UNO Q,
  which broke `arduino-app-cli`. Our scripts reset it.
- **Sensors read lower than datasheets suggest.** Our "sensor unplugged" check
  rejected a working MQ-3, so we lowered the floor to 0.25 % of full scale.
- **Plan for resets.** During development the board sometimes rebooted, and the
  app did not always come back. We never fully pinned down the cause (loose
  wires on the breadboard are our best guess), so we added a keep-alive that
  restarts PGAS within a minute if it is not running.
- **UX matters even for a sensor project.** Our first test took 4 minutes with a
  hood over the food. One sensor at a time, 5 seconds each, guided by the
  phone, it now takes about 15 seconds plus sensor swaps.

## Why Does Open Innovation Matter?

A street vendor can't depend on a subscription, a cloud API or a phone signal.
Everything PGAS uses is open: Arduino App Lab and its bricks, the Arduino
sketch, Python, scikit-learn and ONNX Runtime for on-board inference, and this
code under MIT. Anyone can rebuild it for the cost of a board and three
sensors, retrain it on their own food, or swap in a better model, and no data
ever leaves the stall.

## Prize Categories

**Best Use of Arduino.**

- It **runs a model on the board**: an ONNX model decides with ONNX Runtime on
  the UNO Q, offline.
- It is a **physical agent that senses and acts**: gas sensors in, LED-matrix
  alarm and alert out, with the decision made on the board in under a
  millisecond.
- It uses what makes the UNO Q different: the MCU and Linux working together
  over the Bridge, the built-in LED matrix, and App Lab bricks for the web UI.
- It runs **offline on a power bank**, so it can work at a market stall.

## Limits

- One spoiled sample and one clean-air control is a demo, not an accuracy
  study. The model has seen three real samples and the rule thresholds are
  provisional; both need many more foods.
- MQ sensors need a few minutes of warm-up and drift with temperature and
  humidity.
- PGAS is a reference tool, not a food-safety certification. If in doubt, do
  not eat it, and ask a professional.

## Team

- [@k66inthesky](https://github.com/k66inthesky)
- Built with [Claude Code](https://claude.ai/code) as AI pair programmer
