"""Bag mode: one MQ sensor at a time in a small bag, operator presses Next."""

import json
import threading

import pytest

from pgas import config
from pgas.board import QueueSource, Runtime
from pgas.dataio import load_capture
from pgas.session import NullDisplay, RetestError, SessionError, run_bag
from mock_hw import MockSource

STEP = 1 + 1 + 3  # clean air, move, measure (seconds = readings)


def bag_profile(rise_counts):
    """Each sensor's channel rises only while it is being measured in the bag."""
    def f(i):
        k, j = divmod(i, STEP)
        base = [3000.0, 2500.0, 2800.0]
        if k < 3 and j >= 2:
            base[k] += rise_counts[k]
        return tuple(base)
    return f


def test_run_bag_measures_each_sensor_in_turn(tmp_path):
    waits, steps = [], []
    res = run_bag(MockSource(bag_profile([0, 1000, 0])), NullDisplay(), tmp_path, "check",
                  wait_next=lambda: waits.append(1) or True, log=lambda m: None,
                  progress=lambda st, i, n: steps.append(st))
    assert len(waits) == 2  # before MQ-3 and MQ-2
    assert res.rises["mq135"] == pytest.approx(0, abs=1e-9) and res.rises["mq2"] == pytest.approx(0, abs=1e-9)
    assert res.rises["mq3"] == pytest.approx(config.adc_to_sensor_volts(1000), rel=1e-6)
    assert steps[0] == "baseline:mq135" and "wait:mq3" in steps and steps[-1] == "measure:mq2"
    cap = load_capture(res.csv)
    assert cap.mode == "bag" and len(cap) == 3 * STEP
    assert json.loads(cap.path.with_suffix(".json").read_text())["rises_v"]["mq3"] > 0


def test_run_bag_stopped_while_waiting(tmp_path):
    with pytest.raises(SessionError):
        run_bag(MockSource(), NullDisplay(), tmp_path, "check", wait_next=lambda: False, log=lambda m: None)


def _runtime(tmp_path, profile):
    src = QueueSource()
    ms = MockSource(profile)
    rt = Runtime(source=src, disp=NullDisplay(), data_dir=tmp_path, analyze=lambda *a, **k: {})
    rt.source = type("S", (), {"read": lambda self, t: ms.read(t), "flush": lambda self: None})()
    return rt


def test_runtime_bag_job_grades_with_rule(tmp_path):
    rt = _runtime(tmp_path, bag_profile([0, 0, 2000]))
    rt._wait_next = lambda max_s=0: True
    from pgas import jobs
    jid = jobs.submit(rt.jobs_dir, "bag", label="check")
    assert rt.poll_once()
    for _ in range(200):
        st = jobs.read_status(rt.jobs_dir, jid)
        if st and st["state"] != "running":
            break
        threading.Event().wait(0.05)
    assert st["state"] == "done", st
    assert st["result"]["grade"] == "DO-NOT-SELL" and st["result"]["method"] == "rule"


def test_wait_next_times_out_and_stops(tmp_path):
    rt = _runtime(tmp_path, None)
    with pytest.raises(RetestError):
        rt._wait_next(max_s=0.1)
    rt.stop_event.set()
    assert rt._wait_next(max_s=5) is False
    rt.stop_event.clear()
    threading.Timer(0.1, rt.press_next).start()
    assert rt._wait_next(max_s=5) is True
