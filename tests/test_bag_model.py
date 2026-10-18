import pytest

pytest.importorskip("onnxruntime")
pytest.importorskip("skl2onnx")

from pgas import bag_model, config  # noqa: E402


def _rises(a, b, c):
    return dict(zip(config.SENSORS, (a, b, c)))


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    d = tmp_path_factory.mktemp("models")
    card = bag_model.train(d)
    assert card["classes"] == ["fresh", "spoiled"]
    return bag_model.BagModel(d)


def test_training_samples_are_classified_as_labelled(model):
    for x, y, _ in bag_model.SAMPLES:
        p, _ = model.p_spoiled(_rises(*x))
        assert (p >= bag_model.SPOILING_P) == bool(y)


def test_clean_air_is_fresh_and_milk_is_do_not_sell(model):
    p, ms = model.p_spoiled(_rises(0.0, 0.0, 0.0))
    assert bag_model.grade_from_p(p) == "FRESH" and ms >= 0
    p, _ = model.p_spoiled(_rises(0.02, 0.21, 0.05))
    assert bag_model.grade_from_p(p) == "DO-NOT-SELL"


def test_committed_model_loads():
    assert bag_model.load() is not None
