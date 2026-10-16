import json

import numpy as np
import pytest

from pgas import config, plot, train
from pgas.features import CORE_FEATURES
from synth import make_dataset


@pytest.fixture
def dataset_dir(tmp_path):
    d = tmp_path / "raw"
    make_dataset(d)
    return d


def test_build_dataset(dataset_dir):
    ds = train.build_dataset(dataset_dir)
    assert len(ds) == 6 + 2 * ((12 * 60 - config.CONTINUOUS_BASELINE_ROWS) // 30)
    assert ds.synthetic
    assert len(np.unique(ds.groups)) == 8
    assert set(np.unique(ds.y)) == {0, 1, 2}
    assert ds.X["core"].shape == (len(ds), len(CORE_FEATURES))
    assert np.isnan(ds.X["full"]).any()  # continuous windows have no slope


def test_run_end_to_end_exports_onnx(dataset_dir, tmp_path):
    out, figs = tmp_path / "models", tmp_path / "figs"
    card = train.run(dataset_dir, out, figs)
    assert card["model"] in {"knn_k1", "knn_k3", "knn_k5", "logreg"}
    assert card["feature_set"] == "core"
    assert 0 <= card["loso_accuracy"] <= 1
    assert (out / "pgas_classifier.onnx").stat().st_size > 0
    assert (figs / "confusion_matrix.png").exists()
    assert json.loads((out / "model_card.json").read_text())["synthetic"] is True
    assert np.array(card["confusion_matrix"]).sum() == card["n_samples"]

    # ONNX model agrees with the label space and runs with onnxruntime.
    from pgas.infer import Classifier
    from pgas.features import hood_features
    from pgas.dataio import load_capture, list_captures
    clf = Classifier(out)
    swill = [p for p in list_captures(dataset_dir, "hood") if "swill" in p.name][0]
    pred = clf.predict(hood_features(load_capture(swill)))
    assert pred.grade in config.GRADES
    assert sum(pred.probabilities.values()) == pytest.approx(1, abs=1e-4)


def test_refuses_synthetic_into_repo(dataset_dir):
    with pytest.raises(SystemExit, match="synthetic"):
        train.run(dataset_dir, config.MODELS_DIR, config.FIGURES_DIR)
    with pytest.raises(SystemExit, match="synthetic"):
        plot.run(dataset_dir, config.FIGURES_DIR)


def test_loso_never_trains_on_test_session():
    calls = []

    class Spy:
        def __init__(self):
            self.steps = [("m", self)]
        def __getitem__(self, i):
            return self
        def fit(self, X, y):
            calls.append(set(X[:, 0].tolist()))
            return self
        def predict(self, X):
            return np.zeros(len(X), dtype=int)

    X = np.array([[0.0], [0.0], [1.0], [2.0]])
    y = np.array([0, 1, 0, 1])
    groups = np.array(["a", "a", "b", "c"])
    train.loso_predict(Spy, X, y, groups)
    assert calls == [{1.0, 2.0}, {0.0, 2.0}, {0.0, 1.0}]


def test_plot_outputs(dataset_dir, tmp_path):
    outs = plot.run(dataset_dir, tmp_path / "figs")
    names = sorted(p.name for p in outs)
    assert names == ["hood_fresh_vs_spoiled.png", "spoilage_chicken_room_temp.png", "spoilage_tofu_room_temp.png"]


def test_missing_dht_is_imputed_not_fatal(dataset_dir, tmp_path):
    import math
    from pgas.infer import Classifier
    from pgas.features import hood_features
    from pgas.dataio import load_capture, list_captures
    train.run(dataset_dir, tmp_path / "m", tmp_path / "f")
    clf = Classifier(tmp_path / "m")
    feats = hood_features(load_capture(list_captures(dataset_dir, "hood")[0]))
    feats["temp_c"] = feats["rh_pct"] = math.nan
    pred = clf.predict(feats)
    assert pred.grade in config.GRADES and set(pred.imputed) == {"temp_c", "rh_pct"}
    feats["mq135_d_peak"] = math.nan
    with pytest.raises(ValueError, match="mq135_d_peak"):
        clf.predict(feats)
