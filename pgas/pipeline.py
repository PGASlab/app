"""Capture -> features -> grade -> advice, for one hood capture."""

from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

from . import agent, config
from .dataio import load_capture
from .features import hood_features

_classifier = None


def get_classifier(model_dir: Path = config.MODELS_DIR):
    """Load the ONNX classifier once; None if no model has been trained yet."""
    global _classifier
    if _classifier is None and (Path(model_dir) / "pgas_classifier.onnx").exists():
        from .infer import Classifier

        _classifier = Classifier(model_dir)
    return _classifier


def analyze(csv_path: Path | str, use_llm: bool = True, classifier=None, llm=None) -> dict:
    t0 = time.perf_counter()
    cap = load_capture(csv_path)
    feats = hood_features(cap)
    t_feat = time.perf_counter()
    clf = classifier if classifier is not None else get_classifier()
    out: dict = {"file": Path(csv_path).name, "label": cap.label,
                 "features": {k: round(v, 4) for k, v in feats.items()}}
    if clf is None:
        out["grade"] = None
        out["note"] = "no trained model in models/ yet - run python -m pgas.train on the Mac and redeploy"
        out["timing_s"] = {"features": round(t_feat - t0, 3)}
        return out
    pred = clf.predict(feats)
    t_inf = time.perf_counter()
    kwargs = {"llm": llm} if llm is not None else {}
    adv = agent.advise(pred.grade, feats, cap.label, use_llm=use_llm, **kwargs)
    t_adv = time.perf_counter()
    out.update({
        "grade": pred.grade,
        "probabilities": {k: round(v, 3) for k, v in pred.probabilities.items()},
        "advice": adv.text,
        "advice_source": adv.source,
        "fallback_reason": adv.fallback_reason,
        "timing_s": {
            "features": round(t_feat - t0, 3),
            "inference": round(t_inf - t_feat, 4),
            "advice": round(t_adv - t_inf, 2),
            "total_after_capture": round(t_adv - t0, 2),
        },
    })
    out["advice_detail"] = asdict(adv)
    return out
