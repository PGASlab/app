"""Train the PGAS grade classifier on the Mac and export it to ONNX.

    python -m pgas.train                       # uses data/raw, writes models/ + docs/figures/
    python -m pgas.train --data-dir X --out-dir Y --fig-dir Z

Candidates: kNN (k = 1, 3, 5) and multinomial logistic regression, each behind
a StandardScaler, on the "core" feature set and (when every sample has slopes)
the "full" feature set. Selection is by pooled leave-one-session-out (LOSO)
accuracy: every capture file is one session, and a session never contributes
to the model that is scored on it.

Captures whose JSON sidecar has "synthetic": true are refused when writing
into the repository's models/ or docs/ folders, so test data can never end up
in published results.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config, labeling
from .dataio import load_capture, list_captures
from .features import FEATURE_SETS, continuous_windows, hood_features, vector


@dataclass
class Dataset:
    X: dict[str, np.ndarray]           # feature-set name -> matrix
    y: np.ndarray                       # grade index (into config.GRADES)
    groups: np.ndarray                  # session id
    sources: list[str] = field(default_factory=list)
    synthetic: bool = False

    def __len__(self) -> int:
        return len(self.y)


def build_dataset(data_dir: Path, window_rows: int = 30) -> Dataset:
    rows: list[dict] = []
    y: list[int] = []
    groups: list[str] = []
    sources: list[str] = []
    synthetic = False
    for path in list_captures(data_dir):
        cap = load_capture(path)
        synthetic |= bool(cap.meta.get("synthetic"))
        if cap.mode == "bag":
            continue  # one sensor at a time in a bag: different features, not used for training yet
        if cap.mode == "continuous":
            wins = continuous_windows(cap, window_rows=window_rows, step_rows=window_rows)
            grades = labeling.label_continuous(wins)
            for w, g in zip(wins, grades):
                rows.append(w.features)
                y.append(config.GRADES.index(g))
                groups.append(cap.session_id)
            if wins:
                sources.append(path.name)
        else:
            g = labeling.label_hood(cap.label)
            if g is None:
                continue
            try:
                feats = hood_features(cap)
            except ValueError as e:
                print(f"skip {path.name}: {e}", file=sys.stderr)
                continue
            rows.append(feats)
            y.append(config.GRADES.index(g))
            groups.append(cap.session_id)
            sources.append(path.name)
    X = {}
    for name, cols in FEATURE_SETS.items():
        X[name] = np.array([vector(r, cols) for r in rows], dtype=np.float32).reshape(len(rows), len(cols))
    return Dataset(X=X, y=np.array(y, dtype=np.int64), groups=np.array(groups), sources=sources, synthetic=synthetic)


def candidates():
    from sklearn.linear_model import LogisticRegression
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    out = {f"knn_k{k}": (lambda k=k: make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=k)))
           for k in (1, 3, 5)}
    out["logreg"] = lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
    return out


def loso_predict(make_model, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> np.ndarray | None:
    """Pooled leave-one-session-out predictions, or None if a fold can't be fit."""
    pred = np.full(len(y), -1)
    for g in np.unique(groups):
        test = groups == g
        train = ~test
        if len(np.unique(y[train])) < 2:
            return None
        m = make_model()
        n_neighbors = getattr(m[-1], "n_neighbors", None)
        if n_neighbors is not None and n_neighbors > train.sum():
            return None
        m.fit(X[train], y[train])
        pred[test] = m.predict(X[test])
    return pred


def evaluate(ds: Dataset) -> list[dict]:
    results = []
    for fs_name, X in ds.X.items():
        if np.isnan(X).any():
            results.append({"feature_set": fs_name, "skipped": "contains NaN (no slopes in continuous data)"})
            continue
        for name, make in candidates().items():
            pred = loso_predict(make, X, ds.y, ds.groups)
            if pred is None:
                results.append({"feature_set": fs_name, "model": name, "skipped": "fold not trainable"})
                continue
            results.append({
                "feature_set": fs_name,
                "model": name,
                "loso_accuracy": float((pred == ds.y).mean()),
                "pred": pred,
            })
    return results


def pick_best(results: list[dict]) -> dict | None:
    scored = [r for r in results if "loso_accuracy" in r]
    if not scored:
        return None
    # Highest accuracy; ties go to the simpler model (logreg < knn) and core features.
    order = {"logreg": 0, "knn_k5": 1, "knn_k3": 2, "knn_k1": 3}
    return max(scored, key=lambda r: (r["loso_accuracy"], -order[r["model"]], r["feature_set"] == "core"))


def export_onnx(model, n_features: int, path: Path) -> None:
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    onx = convert_sklearn(
        model,
        initial_types=[("features", FloatTensorType([None, n_features]))],
        options={id(model): {"zipmap": False}},
        target_opset=17,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(onx.SerializeToString())


def plot_confusion(y_true: np.ndarray, y_pred: np.ndarray, title: str, path: Path) -> np.ndarray:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import confusion_matrix

    cm = confusion_matrix(y_true, y_pred, labels=range(len(config.GRADES)))
    fig, ax = plt.subplots(figsize=(4.8, 4.2), dpi=150)
    ax.imshow(cm, cmap="Greens")
    ax.set_xticks(range(3), config.GRADES)
    ax.set_yticks(range(3), config.GRADES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Label")
    ax.set_title(title, fontsize=9)
    for i in range(3):
        for j in range(3):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return cm


def _inside(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def run(data_dir: Path, out_dir: Path, fig_dir: Path, window_rows: int = 30) -> dict:
    ds = build_dataset(data_dir, window_rows=window_rows)
    if ds.synthetic and (_inside(out_dir, config.REPO_ROOT) or _inside(fig_dir, config.REPO_ROOT)):
        raise SystemExit("refusing to publish a model/figure trained on synthetic data inside the repo")
    if len(ds) == 0 or len(np.unique(ds.y)) < 2:
        raise SystemExit(f"not enough labelled data in {data_dir} ({len(ds)} samples)")

    results = evaluate(ds)
    best = pick_best(results)
    if best is None:
        raise SystemExit("no candidate could be evaluated with leave-one-session-out")

    fs = FEATURE_SETS[best["feature_set"]]
    model = candidates()[best["model"]]()
    model.fit(ds.X[best["feature_set"]], ds.y)
    onnx_path = out_dir / "pgas_classifier.onnx"
    export_onnx(model, len(fs), onnx_path)

    cm = plot_confusion(
        ds.y, best["pred"],
        f"LOSO confusion - {best['model']} ({best['feature_set']}), n={len(ds)}",
        fig_dir / "confusion_matrix.png",
    )
    counts = {g: int((ds.y == i).sum()) for i, g in enumerate(config.GRADES)}
    card = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "model": best["model"],
        "feature_set": best["feature_set"],
        "features": list(fs),
        "classes": list(config.GRADES),
        "n_samples": len(ds),
        "n_sessions": int(len(np.unique(ds.groups))),
        "class_counts": counts,
        "window_rows": window_rows,
        "labeling": {
            "spoiling_at": labeling.SPOILING_AT,
            "do_not_sell_at": labeling.DO_NOT_SELL_AT,
            "min_rise_v": labeling.MIN_RISE_V,
        },
        "loso_accuracy": best["loso_accuracy"],
        # Used on the board when the DHT22 gave no valid reading during a capture.
        "feature_medians": {f: float(np.nanmedian(ds.X[best["feature_set"]][:, i])) for i, f in enumerate(fs)},
        "confusion_matrix": cm.tolist(),
        "all_candidates": [{k: v for k, v in r.items() if k != "pred"} for r in results],
        "sources": ds.sources,
        "synthetic": ds.synthetic,
    }
    (out_dir / "model_card.json").write_text(json.dumps(card, indent=2) + "\n")
    return card


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=config.DATA_RAW)
    ap.add_argument("--out-dir", type=Path, default=config.MODELS_DIR)
    ap.add_argument("--fig-dir", type=Path, default=config.FIGURES_DIR)
    ap.add_argument("--window-rows", type=int, default=30, help="continuous-mode window length (rows = minutes)")
    a = ap.parse_args(argv)
    card = run(a.data_dir, a.out_dir, a.fig_dir, a.window_rows)
    for r in card["all_candidates"]:
        acc = r.get("loso_accuracy")
        print(f"{r['feature_set']:5s} {r.get('model', '-'):8s} "
              + (f"LOSO acc = {acc:.3f}" if acc is not None else f"skipped: {r['skipped']}"))
    print(f"selected: {card['model']} on {card['feature_set']} features, LOSO acc = {card['loso_accuracy']:.3f}, "
          f"n = {card['n_samples']} from {card['n_sessions']} sessions")
    print(f"wrote {a.out_dir / 'pgas_classifier.onnx'} and {a.out_dir / 'model_card.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
