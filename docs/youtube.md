# YouTube upload

Thumbnail: [`images/youtube-thumbnail.jpg`](images/youtube-thumbnail.jpg) (1280×720)

## Title

I Gave AI a Nose: Arduino UNO Q Smells Spoiled Milk (On-Board AI, Offline)

## Description

LLMs can read, write, see and listen, but they can't smell. So we built a nose.

PGAS is an AI nose on the Arduino UNO Q. Three gas sensors (MQ-135, MQ-3, MQ-2)
smell the food one at a time, 5 seconds each, guided by a page on your phone.
An ONNX model decides on the board whether the food is fresh or spoiled, and
the board acts: the LED matrix flashes a warning and the phone shows the
verdict. No cloud, no account, no internet, and it runs from a power bank.

Built for night-market stalls and small food side hustles, where selling
spoiled food is a health risk and throwing away good food is waste.

In this video:
- The parts: Arduino UNO Q, breadboard, three MQ gas sensors, power bank
- Clean-air control test: "Food looks fine"
- Guided test on a bottle of spoiled milk, one sensor at a time
- Verdict: DO-NOT-SELL (MQ-3 ethanol rise +0.21 V), LED matrix alarm
- Live gauges: MQ-3 0.37 V in clean air → 0.70 V over the milk → 0.38 V 30 s later

Code (MIT): https://github.com/PGASlab/app
Write-up on DEV: [ARTICLE_URL]
Submission for the DEV Hacktoberfest Open-Source AI Challenge: Side Hustle (Best Use of Arduino).

PGAS is a reference tool, not a food-safety certification. If in doubt, don't eat it.

#Arduino #ArduinoUNOQ #EdgeAI #ONNX #OpenSource #Hacktoberfest
