"""On-board grade inference with the exported ONNX classifier."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config
from .features import vector


# Only environment features may be filled in; a missing gas feature is an error.
IMPUTABLE = ("temp_c", "rh_pct")


@dataclass
class Prediction:
    grade: str
    probabilities: dict[str, float]
    latency_ms: float
    imputed: tuple[str, ...] = ()


class Classifier:
    def __init__(self, model_dir: Path = config.MODELS_DIR):
        import onnxruntime as ort

        model_dir = Path(model_dir)
        self.card = json.loads((model_dir / "model_card.json").read_text())
        self.features = tuple(self.card["features"])
        self.classes = tuple(self.card["classes"])
        self.session = ort.InferenceSession(
            str(model_dir / "pgas_classifier.onnx"), providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name

    def predict(self, features: dict[str, float]) -> Prediction:
        x = vector(features, self.features).reshape(1, -1)
        imputed = []
        medians = self.card.get("feature_medians", {})
        for i, n in enumerate(self.features):
            if np.isnan(x[0, i]) and n in IMPUTABLE and n in medians:
                x[0, i] = medians[n]  # DHT22 gave no valid reading during this capture
                imputed.append(n)
        if np.isnan(x).any():
            missing = [n for n, v in zip(self.features, x[0]) if np.isnan(v)]
            raise ValueError(f"missing features: {missing}")
        t0 = time.perf_counter()
        label, probs = self.session.run(None, {self.input_name: x})
        dt = (time.perf_counter() - t0) * 1000
        p = np.asarray(probs)[0]
        return Prediction(
            grade=self.classes[int(np.asarray(label)[0])],
            probabilities={c: float(p[i]) for i, c in enumerate(self.classes)},
            latency_ms=dt,
            imputed=tuple(imputed),
        )
