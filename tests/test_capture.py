import json
import threading

import pytest

from pgas import capture, config, display, jobs, selftest
from pgas.board import Runtime
from pgas.dataio import COLUMNS, load_capture
from pgas.features import hood_features
from pgas.session import NullDisplay, run_continuous, run_hood
from pgas.dataio import CaptureWriter
from mock_hw import MockSource, hood_profile


def test_hood_session_writes_csv(tmp_path):
    disp = NullDisplay()
    res = run_hood(MockSource(hood_profile(800)), disp, tmp_path, "fresh_chicken", log=lambda m: None)
    cap = load_capture(res.csv)
    assert cap.mode == "hood" and cap.label == "fresh_chicken"
    assert res.csv.endswith("_hood_fresh_chicken.csv")
    phases = list(cap.phase)
    assert phases.count("baseline") == config.HOOD_BASELINE_S
    assert phases.count("move") == 5
    assert phases.count("expose") == config.HOOD_EXPOSE_S
    assert 0 < phases.count("recover") < config.HOOD_RECOVER_MAX_S
    assert res.recovered
    assert cap.t_s[0] == 0 and cap.t_s[1] == 1
    with open(res.csv) as fh:
        assert fh.readline().strip().split(",") == list(COLUMNS)
    meta = json.loads(cap.path.with_suffix(".json").read_text())
    assert meta["recovered"] is True and meta["adc_bits"] == config.ADC_BITS
    f = hood_features(cap)
    assert f["mq135_d_peak"] > 0.2 and f["temp_c"] == 26.5
    # One LED frame per reading; first frame is the 30 s ambient countdown.
    assert len(disp.frames) == len(cap)
    assert disp.frames[0] == display.countdown("A", config.HOOD_BASELINE_S, 0)


def test_hood_session_no_recovery(tmp_path):
    res = run_hood(MockSource(lambda i: (3000 + (900 if i > 35 else 0), 2500, 2800)), NullDisplay(),
                   tmp_path, "swill_x", log=lambda m: None, recover_max_s=20)
    assert not res.recovered
    assert list(load_capture(res.csv).phase).count("recover") == 20


def test_hood_session_fails_without_readings(tmp_path):
    from pgas.session import SessionError
    with pytest.raises(SessionError, match="no sensor reading"):
        run_hood(MockSource(limit=10), NullDisplay(), tmp_path, "fresh_x", log=lambda m: None)
    meta = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert "error" in meta


def test_continuous_one_row_per_minute_and_resume(tmp_path):
    from datetime import datetime
    stop = threading.Event()
    src = MockSource(limit=600)  # 10 minutes of 1 Hz readings
    w = CaptureWriter(tmp_path, "continuous", "chicken_room_temp", datetime(2026, 1, 1))
    t0 = src.t0
    n = run_continuous(src, NullDisplay(), w, t0, stop, until=t0 + 300, log=lambda m: None)
    w.close()
    assert n == 5
    cap = load_capture(w.csv_path)
    assert list(cap.t_s) == [0, 60, 120, 180, 240]
    # Restart: resume appends with a continuous time axis.
    src2 = MockSource(t0=t0 + 300, limit=120, stop_when_done=stop)
    w2 = CaptureWriter.resume(w.csv_path)
    n2 = run_continuous(src2, NullDisplay(), w2, t0, stop, log=lambda m: None)
    w2.close()
    cap = load_capture(w.csv_path)
    assert n2 == 2 and list(cap.t_s) == [0, 60, 120, 180, 240, 300, 360]
    assert json.loads(w.meta_path.read_text())["restarts"] == 1


def test_continuous_dht_missing_written_empty(tmp_path):
    from datetime import datetime
    import math
    stop = threading.Event()
    src = MockSource(limit=120, dht_fail=True, stop_when_done=stop)
    w = CaptureWriter(tmp_path, "continuous", "x", datetime(2026, 1, 1))
    run_continuous(src, NullDisplay(), w, src.t0, stop, log=lambda m: None)
    w.close()
    cap = load_capture(w.csv_path)
    assert all(math.isnan(v) for v in cap.temp_c)


def test_selftest_pass_and_fail():
    good = [MockSource().read(1) for _ in range(20)]
    checks = selftest.evaluate(good, 20)
    assert all(c.ok for c in checks), selftest.report(checks)
    assert selftest.report(checks).endswith("OVERALL: PASS")

    sat = MockSource(lambda i: (config.ADC_MAX, 2500, 2800), dht_fail=True)
    bad = [sat.read(1) for _ in range(20)]
    rep = {c.name: c.ok for c in selftest.evaluate(bad, 20)}
    assert rep["MQ135 on A0 range"] is False
    assert rep["DHT22 on D2"] is False
    drift = MockSource(lambda i: (3000 + 40 * i, 2500, 2800))
    rep = {c.name: c.ok for c in selftest.evaluate([drift.read(1) for _ in range(20)], 20)}
    assert rep["MQ135 stable"] is False
    rep = {c.name: c.ok for c in selftest.evaluate([], 20)}
    assert rep["Bridge (MCU -> Linux)"] is False


def test_display_frames():
    f = display.countdown("H", 42, 0.5)
    assert len(f) == 104 and max(f) == display.ON
    assert sum(1 for x in f[7 * 13:] if x) == round(0.5 * 13)
    for g in config.GRADES:
        assert len(display.icon(g)) == 104
    assert display.to_bytes(display.icon("FRESH"))[0] == 0
    assert len(display.to_bytes(display.countdown("A", 250, 2))) == 104
    with pytest.raises(ValueError):
        display.to_bytes([0] * 10)


# --- job queue + runtime + CLI ---------------------------------------------

class FakeAnalyze:
    def __call__(self, csv, use_llm=True):
        return {"grade": "FRESH", "advice": "The chicken smells fresh: sell as normal.",
                "use_llm": use_llm, "features": {}}


def _runtime(tmp_path, src):
    return Runtime(source=src, disp=NullDisplay(), data_dir=tmp_path, analyze=FakeAnalyze())


def _wait(rt, jobs_dir, job_id, timeout=10):
    import time
    t = time.time()
    while time.time() - t < timeout:
        rt.poll_once()
        st = jobs.read_status(jobs_dir, job_id)
        if st and st["state"] in jobs.FINAL:
            return st
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish: {st}")


def test_runtime_hood_job(tmp_path, monkeypatch):
    monkeypatch.setenv("PGAS_TELEGRAM_TOKEN", "")
    from pgas import notify
    monkeypatch.setattr(notify, "OUTBOX", tmp_path / "outbox.jsonl")
    rt = _runtime(tmp_path, MockSource(hood_profile(800)))
    jid = jobs.submit(rt.jobs_dir, "hood", label="fresh_chicken", use_llm=False)
    st = _wait(rt, rt.jobs_dir, jid)
    assert st["state"] == "done", st
    assert st["result"]["grade"] == "FRESH" and st["result"]["use_llm"] is False
    assert any("GRADE: FRESH" in ln for ln in st["lines"])
    csvs = list((tmp_path / "raw").glob("*_hood_fresh_chicken.csv"))
    assert len(csvs) == 1
    meta = json.loads(csvs[0].with_suffix(".json").read_text())
    assert meta["onboard_result"]["grade"] == "FRESH"
    assert rt.disp.frames[-1] == display.icon("FRESH")


def test_runtime_rejects_second_capture_and_stops_continuous(tmp_path):
    import time
    src = MockSource(step=1.0)
    rt = _runtime(tmp_path, src)
    # Slow the mock down so the continuous job keeps running.
    orig = src.read
    src.read = lambda timeout: (time.sleep(0.001), orig(timeout))[1]
    jid = jobs.submit(rt.jobs_dir, "continuous", label="tofu_room_temp")
    rt.poll_once()
    for _ in range(200):
        st = jobs.read_status(rt.jobs_dir, jid)
        if st and any("recording to" in ln for ln in st["lines"]):
            break
        time.sleep(0.01)
    assert (rt.jobs_dir / "continuous.json").exists()
    busy = jobs.submit(rt.jobs_dir, "hood", label="fresh_x")
    st = _wait(rt, rt.jobs_dir, busy)
    assert st["state"] == "rejected"
    stop = jobs.submit(rt.jobs_dir, "stop")
    _wait(rt, rt.jobs_dir, stop)
    st = _wait(rt, rt.jobs_dir, jid)
    assert st["state"] == "done" and st["result"]["rows"] >= 1
    assert not (rt.jobs_dir / "continuous.json").exists()


def test_runtime_selftest_job(tmp_path):
    rt = _runtime(tmp_path, MockSource())
    st = jobs.Status(rt.jobs_dir, "t1", "selftest")
    rt._selftest(st, duration_s=0.2)
    # The mock delivers readings instantly, so the 0.2 s window sees far more
    # than 1 Hz: the Bridge-rate check must flag it, the sensor checks pass.
    assert st.data["state"] == "failed"
    assert any("[PASS] MQ135 stable" in ln for ln in st.data["lines"])
    assert list((tmp_path / "selftest").glob("*.txt"))


def test_cli_follows_job(tmp_path, capsys):
    """CLI submits a job and prints the app's status lines."""
    jobs_dir = tmp_path / "jobs"

    def fake_app():
        import time
        for _ in range(500):
            j = jobs.claim(jobs_dir)
            if j:
                st = jobs.Status(jobs_dir, j["id"], j["kind"])
                st.log(f"label={j['params']['label']}")
                st.finish("done", {"grade": "FRESH"})
                return
            time.sleep(0.01)

    th = threading.Thread(target=fake_app)
    th.start()
    rc = capture.main(["--mode", "hood", "--label", "fresh_chicken", "--jobs-dir", str(jobs_dir)])
    th.join()
    out = capsys.readouterr().out
    assert rc == 0 and "label=fresh_chicken" in out and '"grade": "FRESH"' in out


def test_cli_label_validation():
    with pytest.raises(SystemExit):
        capture.main(["--mode", "hood", "--label", "Fresh Chicken"])
    with pytest.raises(SystemExit):
        capture.main(["--mode", "hood"])


def test_cli_remote_command():
    ap = capture.build_parser()
    argv = ["--host", "pgas.local", "--mode", "hood", "--label", "fresh_chicken"]
    cmd = capture.remote_command(argv, ap.parse_args(argv))
    assert cmd[:3] == ["ssh", "-t", "arduino@pgas.local"]
    assert cmd[3].endswith("python3 -m pgas.capture --mode hood --label fresh_chicken")
    argv = ["--adb", "--selftest"]
    cmd = capture.remote_command(argv, ap.parse_args(argv))
    assert cmd[:2] == ["adb", "shell"] and cmd[2].endswith("python3 -m pgas.capture --selftest")


def test_cli_times_out_without_app(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "follow", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("not running")))
    assert capture.main(["--selftest", "--jobs-dir", str(tmp_path)]) == 2
    assert list((tmp_path / "pending").glob("*.json"))


@pytest.mark.parametrize("fail_at,step", [(5, "step 1/3"), (32, "step 2/3 (move)"), (60, "step 2/3 (over the food)"),
                                          (100, "step 3/3")])
def test_disconnected_sensor_asks_for_retest(tmp_path, fail_at, step):
    from pgas.session import RetestError
    profile = hood_profile(800)
    src = MockSource(lambda i: (0.0, *profile(i)[1:]) if i >= fail_at else profile(i))
    with pytest.raises(RetestError, match="please re-test") as e:
        run_hood(src, NullDisplay(), tmp_path, "fresh_x", log=lambda m: None)
    assert e.value.step.startswith(step) and "MQ135" in e.value.reason


def test_strong_smell_at_full_scale_is_not_an_error(tmp_path):
    res = run_hood(MockSource(lambda i: (config.ADC_MAX, 2500, 2800)), NullDisplay(), tmp_path, "swill_x",
                   log=lambda m: None, recover_max_s=10)
    assert res.rows > 0


def test_runtime_reports_retest(tmp_path):
    rt = _runtime(tmp_path, MockSource(limit=12))
    jid = jobs.submit(rt.jobs_dir, "hood", label="fresh_x", use_llm=False)
    import time
    t = time.time()
    while time.time() - t < 15:
        rt.poll_once()
        st = jobs.read_status(rt.jobs_dir, jid)
        if st and st["state"] in jobs.FINAL:
            break
        time.sleep(0.05)
    assert st["state"] == "failed" and st["result"]["retest"] is True
    assert any(ln.split(" ", 1)[1].startswith("RETEST:") for ln in st["lines"])
    assert rt.disp.frames[-1] == display.text3("E")
