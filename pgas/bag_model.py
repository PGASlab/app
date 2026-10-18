"""On-board classifier for the guided bag test: three gas rises -> fresh / spoiled.

Input: the rise of each MQ sensor over its own clean-air reading (volts at the
module output), in the order of config.SENSORS. Output: P(spoiled). It runs on
the UNO Q with ONNX Runtime; the model is a scikit-learn logistic regression.

Training data. These are the only labelled bag-style measurements we have,
read off the dashboard during real tests on the board:

    fresh    clean-air control, no food             (photo 02)   +0.03 +0.02 +0.00
    spoiled  spoiled milk, guided test               (photo 09)   +0.02 +0.21 +0.05
    spoiled  spoiled milk, first dashboard test      (chart)      +0.38 +0.41 +0.29

Three samples is far too few to measure accuracy, so the model is a first
step, not a validated classifier. Each sample is repeated with Gaussian noise
of SIGMA_V, the spread the self-test measured on a sensor at rest (readings
stable within 0.02 V), so the boundary is not fitted to three points alone.
Add new labelled rises to SAMPLES and retrain:

    python -m pgas.bag_model            # writes models/pgas_bag.onnx + pgas_bag_card.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import config

MODEL = "pgas_bag.onnx"
CARD = "pgas_bag_card.json"
SIGMA_V = 0.01
COPIES = 200
SEED = 26

# (MQ-135, MQ-3, MQ-2) rises in volts, label (0 fresh, 1 spoiled), source.
SAMPLES = [
    ((0.03, 0.02, 0.00), 0, "clean-air control, docs/images/02-clean-air-fresh.jpg"),
    ((0.02, 0.21, 0.05), 1, "spoiled milk, guided test, docs/images/09-result-do-not-sell.jpg"),
    ((0.38, 0.41, 0.29), 1, "spoiled milk, first dashboard test (read from the chart)"),
]

# P(spoiled) -> grade. Between the two cut-offs the model is unsure.
SPOILING_P = 0.5
SPOILED_P = 0.8


def grade_from_p(p: float) -> str:
    if p >= SPOILED_P:
        return "DO-NOT-SELL"
    if p >= SPOILING_P:
        return "SPOILING"
    return "FRESH"


def dataset(samples=SAMPLES, sigma: float = SIGMA_V, copies: int = COPIES, seed: int = SEED):
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for x, y, _ in samples:
        xs.append(np.asarray(x, dtype=np.float32) + rng.normal(0, sigma, (copies, 3)).astype(np.float32))
        ys.append(np.full(copies, y))
    return np.vstack(xs), np.concatenate(ys)


def train(model_dir: Path = config.MODELS_DIR) -> dict:
    from sklearn.linear_model import LogisticRegression

    from .train import export_onnx

    x, y = dataset()
    clf = LogisticRegression(C=10.0, max_iter=1000).fit(x, y)
    model_dir = Path(model_dir)
    export_onnx(clf, 3, model_dir / MODEL)
    card = {
        "model": "logistic regression (scikit-learn) -> ONNX",
        "inputs": [f"{s}_rise_v" for s in config.SENSORS],
        "classes": ["fresh", "spoiled"],
        "grade_cutoffs": {"SPOILING": SPOILING_P, "DO-NOT-SELL": SPOILED_P},
        "training_samples": [{"rises_v": list(x0), "label": ["fresh", "spoiled"][y0], "source": src}
                             for x0, y0, src in SAMPLES],
        "augmentation": f"{COPIES} copies per sample, Gaussian noise sigma {SIGMA_V} V",
        "note": "3 real samples; no held-out accuracy can be measured yet",
        "coef": [round(float(c), 3) for c in clf.coef_[0]],
        "intercept": round(float(clf.intercept_[0]), 3),
    }
    (model_dir / CARD).write_text(json.dumps(card, indent=2) + "\n")
    return card


class BagModel:
    def __init__(self, model_dir: Path = config.MODELS_DIR):
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(Path(model_dir) / MODEL), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def p_spoiled(self, rises: dict[str, float]) -> tuple[float, float]:
        """P(spoiled) and inference time in ms."""
        x = np.array([[rises[s] for s in config.SENSORS]], dtype=np.float32)
        t0 = time.perf_counter()
        _, probs = self.session.run(None, {self.input_name: x})
        return float(np.asarray(probs)[0][1]), (time.perf_counter() - t0) * 1000


_model = None


def load(model_dir: Path = config.MODELS_DIR):
    """The bag model, or None if it is missing or ONNX Runtime is unavailable."""
    global _model
    if _model is None and (Path(model_dir) / MODEL).exists():
        try:
            _model = BagModel(model_dir)
        except Exception as e:  # noqa: BLE001
            print(f"bag model: not loaded ({e})", flush=True)
    return _model


if __name__ == "__main__":
    c = train()
    print(json.dumps({k: c[k] for k in ("coef", "intercept", "note")}))
