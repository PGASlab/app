"""LiveFeed (pgas/web.py): payloads for the Wi-Fi dashboard."""

import json
import subprocess
import sys

import pytest

from pgas import config, jobs
from pgas.board import QueueSource, Runtime
from pgas.session import NullDisplay
from pgas.web import FeedStatus, LiveFeed


class Sink:
    def __init__(self):
        self.sent = []

    def send_message(self, event, payload, room=None):
        self.sent.append((event, payload, room))


class BrokenSink:
    def __init__(self):
        self.calls = 0

    def send_message(self, event, payload, room=None):
        self.calls += 1
        raise RuntimeError("socket gone")


def test_web_imports_without_arduino():
    code = "import sys, pgas.web, pgas.board; assert not any(m.startswith('arduino') for m in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=config.REPO_ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_sample_payload_values():
    sink = Sink()
    feed = LiveFeed(sink, clock=lambda: 1000.5)
    feed.sample(8000, 4000, 12000, 24.56, 61.04, 1, job="hood job X")
    (event, p, room), = sink.sent
    assert event == "pgas_sample" and room is None
    assert p["ts"] == 1000.5
    assert p["mq135_v"] == pytest.approx(config.adc_to_sensor_volts(8000), abs=1e-3)
    assert p["mq3_v"] == pytest.approx(config.adc_to_sensor_volts(4000), abs=1e-3)
    assert p["mq2_v"] == pytest.approx(config.adc_to_sensor_volts(12000), abs=1e-3)
    assert p["raw"] == [8000, 4000, 12000]
    assert p["temp_c"] == 24.6 and p["rh_pct"] == 61.0 and p["dht_ok"] is True
    assert p["job"] == "hood job X"
    json.dumps(p)  # must be JSON-able for Socket.IO


def test_full_scale_is_module_volts_not_pin_volts():
    sink = Sink()
    LiveFeed(sink).sample(config.ADC_MAX, 0, 0, 20, 50, 1)
    p = sink.sent[0][1]
    assert p["mq135_v"] == pytest.approx(config.ADC_VREF / config.DIVIDER_RATIO, abs=1e-3)
    assert p["mq3_v"] == 0.0


def test_dht_failure_and_bad_numbers():
    sink = Sink()
    LiveFeed(sink).sample(100, float("nan"), "x", 99.0, 99.0, 0)
    p = sink.sent[0][1]
    assert p["temp_c"] is None and p["rh_pct"] is None and p["dht_ok"] is False
    assert p["mq3_v"] is None and p["mq2_v"] is None and p["job"] is None
    json.dumps(p, allow_nan=False)


def test_never_raises_when_send_message_throws():
    sink = BrokenSink()
    feed = LiveFeed(sink)
    for _ in range(5):
        feed.sample(1, 2, 3, 20, 50, 1)
    feed.job_line("id", "hood", "STEP 1/3")
    feed.job_done("id", "hood", "done", {"grade": "FRESH", "advice": "ok"})
    feed.on_connect("sid")
    assert sink.calls == 8 and feed.errors == 8


def test_never_raises_with_no_send_message():
    feed = LiveFeed(object())
    assert feed.sample(1, 2, 3, 20, 50, 1) is not None


def test_history_sent_to_new_client_only():
    sink = Sink()
    t = iter(range(100, 1000))
    feed = LiveFeed(sink, clock=lambda: next(t), history_s=3)
    for i in range(5):
        feed.sample(i, i, i, 20, 50, 1)
    feed.job_done("j1", "hood", "done", {"grade": "SPOILING", "advice": "sell today",
                                          "features": [1.0, 2.0]})
    sink.sent.clear()
    feed.on_connect("abc")
    (event, p, room), = sink.sent
    assert event == "pgas_history" and room == "abc"
    assert [s["raw"][0] for s in p["samples"]] == [2, 3, 4]
    assert p["last_job"]["grade"] == "SPOILING" and "features" not in p["last_job"]


def test_job_done_payload_is_json_safe():
    sink = Sink()
    LiveFeed(sink).job_done("j", "hood", "failed", {"error": ValueError("boom"), "retest": True,
                                                   "step": "baseline"})
    p = sink.sent[0][1]
    assert p == {"ts": p["ts"], "id": "j", "kind": "hood", "state": "failed", "error": "boom",
                 "retest": True, "step": "baseline"}
    json.dumps(p)


def test_runtime_calls_feed(tmp_path):
    sink = Sink()
    feed = LiveFeed(sink)
    src = QueueSource()
    rt = Runtime(source=src, disp=NullDisplay(), data_dir=tmp_path, analyze=lambda *a, **k: {},
                 feed=feed)
    rt.current = "continuous job 42"
    rt.on_sample(3000, 2500, 2800, 25.0, 60.0, 1)
    assert src.read(0.1) is not None  # the reading still reaches the session queue
    (event, p, _), = sink.sent
    assert event == "pgas_sample" and p["raw"] == [3000, 2500, 2800] and p["job"] == "continuous job 42"


def test_runtime_survives_broken_feed(tmp_path):
    src = QueueSource()
    rt = Runtime(source=src, disp=NullDisplay(), data_dir=tmp_path, analyze=lambda *a, **k: {},
                 feed=LiveFeed(BrokenSink()))
    rt.on_sample(3000, 2500, 2800, 25.0, 60.0, 1)
    assert src.read(0.1) is not None


def test_runtime_without_feed(tmp_path):
    src = QueueSource()
    rt = Runtime(source=src, disp=NullDisplay(), data_dir=tmp_path, analyze=lambda *a, **k: {})
    rt.on_sample(3000, 2500, 2800, 25.0, 60.0, 1)
    assert src.read(0.1) is not None


def test_job_lines_and_result_reach_feed(tmp_path):
    sink = Sink()
    rt = Runtime(source=QueueSource(), disp=NullDisplay(), data_dir=tmp_path,
                 analyze=lambda *a, **k: {}, feed=LiveFeed(sink))
    jobs.submit(rt.jobs_dir, "stop")
    assert rt.poll_once()
    events = [(e, p["state"], p.get("line")) for e, p, _ in sink.sent]
    assert events == [("pgas_job", "running", "nothing is running"), ("pgas_job", "done", None)]
    # The status file is still written as before.
    st_files = list((rt.jobs_dir / "status").glob("*.json"))
    assert json.loads(st_files[0].read_text())["state"] == "done"


def test_feed_status_never_raises():
    class St:
        data = {"id": "x", "kind": "hood"}

        def log(self, line):
            self.line = line

        def finish(self, state, result=None):
            self.state = state

    st = St()
    fs = FeedStatus(st, LiveFeed(BrokenSink()))
    fs.log("hello")
    fs.finish("done", {"grade": "FRESH"})
    assert st.line == "hello" and st.state == "done" and fs.data["id"] == "x"


# --- pgas_command: buttons on the dashboard queue the same jobs as the CLI ---

from pgas.web import command  # noqa: E402


def _pending(tmp_path):
    return [json.loads(p.read_text()) for p in sorted((tmp_path / "pending").glob("*.json"))]


def test_command_hood_queues_labelled_job(tmp_path):
    r = command(tmp_path, {"action": "hood", "food": " Soymilk Soup ", "state": "fresh"})
    assert r["ok"] and r["label"] == "fresh_soymilk_soup"
    (job,) = _pending(tmp_path)
    assert job["kind"] == "hood" and job["params"] == {"label": "fresh_soymilk_soup"} and job["id"] == r["id"]


@pytest.mark.parametrize("data,err", [
    ({"action": "hood", "food": "雞肉", "state": "fresh"}, "bad_food"),
    ({"action": "hood", "food": "", "state": "fresh"}, "bad_food"),
    ({"action": "hood", "food": "a" * 41, "state": "fresh"}, "bad_food"),
    ({"action": "hood", "food": "../x", "state": "fresh"}, "bad_food"),
    ({"action": "hood", "food": "rice", "state": "rotten"}, "bad_state"),
    ({"action": "continuous"}, "bad_action"),
    (None, "bad_action"),
])
def test_command_rejects_bad_input(tmp_path, data, err):
    r = command(tmp_path, data)
    assert not r["ok"] and r["error"] == err
    assert _pending(tmp_path) == []


@pytest.mark.parametrize("action", ["selftest", "stop"])
def test_command_selftest_and_stop(tmp_path, action):
    r = command(tmp_path, {"action": action})
    assert r["ok"]
    assert [j["kind"] for j in _pending(tmp_path)] == [action]


def test_command_job_runs_through_runtime(tmp_path):
    feed = LiveFeed(Sink())
    rt = Runtime(source=QueueSource(), disp=NullDisplay(), data_dir=tmp_path, analyze=lambda *a, **k: {}, feed=feed)
    command(rt.jobs_dir, {"action": "stop"})
    assert rt.poll_once()
    (st,) = [json.loads(p.read_text()) for p in (rt.jobs_dir / "status").glob("*.json")]
    assert st["kind"] == "stop" and st["state"] == "done"


def test_reply_goes_to_one_browser():
    sink = Sink()
    feed = LiveFeed(sink)
    feed.reply("sid-1", {"ok": True})
    feed.reply(None, {"ok": False})
    assert sink.sent == [("pgas_command_reply", {"ok": True}, "sid-1"), ("pgas_command_reply", {"ok": False}, None)]


def test_command_check_is_one_button_hood(tmp_path):
    r = command(tmp_path, {"action": "check"})
    assert r["ok"] and r["label"] == "check"
    (job,) = _pending(tmp_path)
    assert job["kind"] == "hood" and job["params"] == {"label": "check"}


def test_progress_and_rule_result_reach_the_page():
    sink = Sink()
    feed = LiveFeed(sink, clock=lambda: 5.0)
    feed.job_progress("j1", "hood", "expose", 10, 60)
    feed.job_done("j1", "hood", "done", {"grade": "FRESH", "method": "rule", "rises_v": {"mq135": 0.01234}})
    (_, prog, _), (_, done, _) = sink.sent
    assert prog["phase"] == "expose" and prog["i"] == 10 and prog["n"] == 60
    assert done["grade"] == "FRESH" and done["method"] == "rule" and done["rises_v"] == {"mq135": 0.012}
