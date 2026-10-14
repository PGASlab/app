# Demo video script (about 80 s)

Shoot vertical or horizontal, but keep the LED matrix in focus whenever it is
on screen: it is the main piece of UI. Overlay text is in English. Audio is
optional; if you narrate, read the voice-over (VO) lines.

| # | Time | Shot | On screen | VO / overlay text |
|---|---|---|---|---|
| 1 | 0–6 s | Close-up: a silver spoon next to a bowl of food on a night-market style table. | — | Overlay: *"For centuries, people tested food with a silver spoon."* |
| 2 | 6–12 s | The spoon is set down; cut to the PGAS box (K-812) with the UNO Q next to it. | Logo bottom-right (assets/pgas-org-logo.png). | Overlay: *"PGAS is the modern silver spoon: an AI nose."* |
| 3 | 12–20 s | Inside of the box, slow pan over the three MQ sensors and the DHT22. | Labels: MQ-135 ammonia/sulfides · MQ-3 ethanol · MQ-2 VOCs | VO: *"Three gas sensors smell what spoiling food releases."* |
| 4 | 20–26 s | Over the shoulder: type `python3 -m pgas.capture --mode hood --label fresh_chicken` (laptop or phone ssh). | Terminal readable. | Overlay: *"Fully offline. Nothing leaves the board."* |
| 5 | 26–34 s | Box held in open air; LED matrix close-up shows **A** and the countdown. | Matrix: `A 30 → A 01`, progress bar filling. | Overlay: *"1. Smell the air."* (speed up 4×) |
| 6 | 34–46 s | Box lowered over **fresh** chicken, 3–5 cm above, not touching. Matrix shows **M** then **H**. | Matrix: `M 05`, then `H 60 → H 01`. | Overlay: *"2. Hood over the food for 60 s."* (speed up 6×) |
| 7 | 46–52 s | Box lifted; matrix shows **V**, then the **✓** icon. Terminal prints GRADE: FRESH and the advice line. | Freeze 2 s on the real terminal output. | Overlay: *"FRESH"* |
| 8 | 52–66 s | Repeat with the **spoiled sample / swill** (cut straight to the result to save time). Matrix shows **✗**; terminal shows DO-NOT-SELL and the advice. | Freeze 2 s on the real terminal output. | Overlay: *"DO-NOT-SELL"* |
| 9 | 66–74 s | Screen capture of the spoilage curve (docs/figures/spoilage_*.png) and the confusion matrix. | Real figures only. | Overlay: *"Trained on our own spoilage recordings."* |
| 10 | 74–82 s | Board running from the power bank, Wi-Fi off icon or unplugged router. Logo + repo URL. | `github.com/PGASlab/app` | Overlay: *"Open source. Offline. Zero running cost."* |

Rules for the edit:
* Only show grades and advice that the board really produced in that take. Do
  not re-type or stage the terminal output.
* If the advice in the take came from the rule-based fallback, that's fine.
  Don't cut it out.
* Speed-ups must be labelled (e.g. "4×").
