from pgas import config, pipeline, train
from pgas.infer import Classifier
from pgas.session import NullDisplay, run_hood
from mock_hw import MockSource, hood_profile
from synth import make_dataset


def test_capture_to_grade_to_advice(tmp_path):
    make_dataset(tmp_path / "raw")
    train.run(tmp_path / "raw", tmp_path / "models", tmp_path / "figs")
    clf = Classifier(tmp_path / "models")
    res = run_hood(MockSource(hood_profile(3000)), NullDisplay(), tmp_path / "live", "swill_test",
                   log=lambda m: None)
    out = pipeline.analyze(res.csv, classifier=clf, llm=lambda p, t: (_ for _ in ()).throw(RuntimeError("off")))
    assert out["grade"] in config.GRADES
    assert out["advice_source"] == "rules" and "off" in out["fallback_reason"]
    assert out["timing_s"]["total_after_capture"] >= 0
    assert out["advice"]


def test_analyze_without_model_uses_gas_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "get_classifier", lambda: None)
    weak = run_hood(MockSource(hood_profile(0)), NullDisplay(), tmp_path, "check", log=lambda m: None)
    out = pipeline.analyze(weak.csv)
    assert out["method"] == "rule" and out["grade"] == "FRESH" and out["advice"]
    assert set(out["rises_v"]) == set(config.SENSORS)
    strong = run_hood(MockSource(hood_profile(3000)), NullDisplay(), tmp_path, "check", log=lambda m: None)
    assert pipeline.analyze(strong.csv)["grade"] == "DO-NOT-SELL"


def test_app_layout_detection(tmp_path):
    import importlib.util, shutil, sys
    app = tmp_path / "pgas_app"
    (app / "python").mkdir(parents=True)
    (app / "app.yaml").write_text("name: PGAS\n")
    shutil.copytree(config.REPO_ROOT / "pgas", app / "python" / "pgas")
    spec = importlib.util.spec_from_file_location("pgas_cfg_probe", app / "python" / "pgas" / "config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.APP_ROOT == app.resolve()
    assert mod.JOBS_DIR == app.resolve() / "data" / "jobs"
