# How training labels are made

The labels are reproducible: `python -m pgas.train` derives them from the raw
CSVs with the code in [`pgas/labeling.py`](../pgas/labeling.py). Nothing is
hand-edited.

## Continuous captures (food left for 24–48 h)

1. **Windows.** Rows 1–10 (the first 10 minutes) form the fresh baseline. The
   rest is cut into non-overlapping 30-row windows (30 minutes).
2. **Rise per sensor.** For each window and each MQ sensor, take `d_median`:
   the window median minus the baseline median, in volts at the module output.
   Negative values are clipped to 0.
3. **Normalise.** Divide each sensor's rise by the largest rise that sensor shows
   anywhere in the same recording. A sensor whose largest rise is under
   **0.05 V** counts as not responding to this food and contributes 0.
4. **Spoilage index** = mean of the three normalised rises (0 … 1).
5. **Monotonic.** Take the running maximum of the index, because spoilage does
   not reverse. The index never goes down, even if a door opened and the air
   cleared for a moment.
6. **Grade.**

   | index | grade |
   |---|---|
   | < 0.25 | FRESH |
   | 0.25 – 0.60 | SPOILING |
   | ≥ 0.60 | DO-NOT-SELL |

The thresholds are design choices, not measurements. They live in
`pgas/labeling.py` (`SPOILING_AT`, `DO_NOT_SELL_AT`, `MIN_RISE_V`), and the
values used for each model are copied into `models/model_card.json`.

Limitation: step 3 assumes that every recording ends clearly spoiled. That holds
for 24–48 h at room temperature for the foods used here, but not for a
refrigerated recording, which would need the per-recording normalisation
replaced by fixed volt thresholds.

## Hood captures

The operator picks the label when capturing. Its prefix is the grade:

| label prefix | grade |
|---|---|
| `fresh_` | FRESH |
| `spoiling_` | SPOILING |
| `spoiled_`, `swill_` | DO-NOT-SELL |
| anything else | not used for training |

## Model selection

Every capture file is one *session*. Leave-one-session-out (LOSO) means each
session is predicted by a model that never saw it. PGAS compares kNN (k = 1, 3, 5)
and logistic regression, each behind a StandardScaler. It picks the one with the
best pooled LOSO accuracy; on a tie it takes the simpler model. The confusion
matrix in `docs/figures/confusion_matrix.png` comes from those pooled LOSO
predictions on real captures only. Captures marked `"synthetic": true` (test
fixtures) are refused.

Continuous mode logs one row per minute, so the 20 s rise slope cannot be
computed there. The default ("core") feature set therefore leaves the slopes out.
The "full" set, with slopes, is evaluated only when every sample has them.
