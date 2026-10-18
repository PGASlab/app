"""Runtime of the PGAS App Lab app (runs inside the app's Python container).

* The sketch calls Bridge.notify("pgas_sample", a0, a1, a2, temp_c, rh_pct,
  dht_ok) once per second; `on_sample` queues the reading.
* A worker thread takes jobs from data/jobs/pending (written by
  `python -m pgas.capture`) and runs hood / continuous / selftest sessions.
* Frames for the LED matrix go back to the sketch with Bridge.call("draw", ...).
* With an optional `feed` (pgas.web.LiveFeed) every sample, job log line and
  result is also pushed to the Wi-Fi dashboard served by the web_ui brick.
* A continuous capture survives an app restart: its state is kept in
  data/jobs/continuous.json and the app resumes appending on start.
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
from pathlib import Path

from . import agent, config, display, jobs, notify, rules, selftest
from .dataio import CaptureWriter
from .session import (BAG_WAIT_MAX_S, ContinuousState, Reading, RetestError, run_bag, run_continuous,
                      run_hood)


class QueueSource:
    def __init__(self, maxsize: int = 600):
        self.q: queue.Queue[Reading] = queue.Queue(maxsize=maxsize)

    def put(self, r: Reading) -> None:
        try:
            self.q.put_nowait(r)
        except queue.Full:
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass
            self.q.put_nowait(r)

    def read(self, timeout: float) -> Reading | None:
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self) -> None:
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                return


class BridgeDisplay:
    def __init__(self, bridge):
        self.bridge = bridge
        self.last: bytes | None = None

    def show(self, frame: list[int]) -> None:
        data = display.to_bytes(frame)
        if data == self.last:
            return
        try:
            self.bridge.call("draw", data, timeout=2)
            self.last = data
        except Exception as e:  # noqa: BLE001 - display is best effort
            print(f"draw failed: {e}", flush=True)


class Runtime:
    def __init__(self, bridge=None, source: QueueSource | None = None, disp=None,
                 data_dir: Path = config.DATA_DIR, analyze=None, feed=None):
        self.source = source or QueueSource()
        self.disp = disp or BridgeDisplay(bridge)
        self.data_dir = Path(data_dir)
        self.jobs_dir = self.data_dir / "jobs"
        self.raw_dir = self.data_dir / "raw"
        self.state_path = self.jobs_dir / "continuous.json"
        self.busy = threading.Lock()
        self.stop_event = threading.Event()
        self.current: str | None = None
        self.next_event = threading.Event()  # "Next sensor" pressed on the dashboard
        self.feed = feed  # pgas.web.LiveFeed or None; its methods never raise
        if analyze is None:
            from .pipeline import analyze
        self.analyze = analyze

    # Bridge handler: keep it short (runs on the Bridge thread).
    def on_sample(self, a0, a1, a2, temp_c, rh_pct, dht_ok=1):
        ok = bool(dht_ok)
        self.source.put(Reading(time.time(), float(a0), float(a1), float(a2),
                                float(temp_c) if ok else None, float(rh_pct) if ok else None))
        if self.feed is not None:
            self.feed.sample(a0, a1, a2, temp_c, rh_pct, dht_ok, job=self.current)

    def _status(self, job_id: str, kind: str):
        st = jobs.Status(self.jobs_dir, job_id, kind)
        if self.feed is None:
            return st
        from .web import FeedStatus

        return FeedStatus(st, self.feed)

    # --- job handling -------------------------------------------------------
    def poll_once(self) -> bool:
        job = jobs.claim(self.jobs_dir)
        if job is None:
            return False
        kind = job["kind"]
        st = self._status(job["id"], kind)
        if kind == "stop":
            if self.current:
                self.stop_event.set()
                st.log(f"stopping {self.current}")
            else:
                st.log("nothing is running")
            self.state_path.unlink(missing_ok=True)
            st.finish("done")
            return True
        if not self.busy.acquire(blocking=False):
            st.log(f"busy: {self.current} is running (stop it with: python3 -m pgas.capture --stop)")
            st.finish("rejected")
            return True
        self.stop_event.clear()
        self.current = f"{kind} job {job['id']}"
        threading.Thread(target=self._run, args=(job, st), daemon=True).start()
        return True

    def _run(self, job: dict, st: jobs.Status, resume: ContinuousState | None = None) -> None:
        try:
            kind, p = job["kind"], job.get("params", {})
            if kind == "hood":
                res = run_hood(self.source, self.disp, self.raw_dir, p["label"], log=st.log,
                               stop=self.stop_event, progress=getattr(st, "progress", None))
                st.log("analysing...")
                if hasattr(st, "progress"):
                    st.progress("analyse", 0, 1)
                out = self.analyze(res.csv, use_llm=p.get("use_llm", True))
                out["capture_s"] = round(res.capture_s, 1)
                out["recovered"] = res.recovered
                if out.get("grade"):
                    self.disp.show(display.icon(out["grade"]))
                    st.log(f"GRADE: {out['grade']}")
                    st.log(f"ADVICE: {out['advice']}")
                    out["notify"] = notify.send(f"PGAS {out['grade']} - {out['advice']}")
                else:
                    st.log(out.get("note", "no grade"))
                _annotate(Path(res.csv), out)
                st.finish("done", out)
            elif kind == "bag":
                self._bag(p, st)
            elif kind == "continuous":
                self._continuous(job, st, resume)
            elif kind == "selftest":
                self._selftest(st)
            else:
                st.log(f"unknown job kind {kind}")
                st.finish("failed")
        except RetestError as e:
            st.log(f"RETEST: {e}")
            self.disp.show(display.text3("E"))
            st.finish("failed", {"error": str(e), "retest": True, "step": e.step})
        except Exception as e:  # noqa: BLE001
            st.log(f"ERROR: {e}")
            traceback.print_exc()
            self.disp.show(display.text3("E"))
            st.finish("failed", {"error": str(e)})
        finally:
            self.current = None
            self.busy.release()

    def press_next(self) -> None:
        self.next_event.set()

    def _wait_next(self, max_s: float = BAG_WAIT_MAX_S) -> bool:
        self.next_event.clear()
        t0 = time.monotonic()
        while not self.next_event.wait(0.5):
            if self.stop_event.is_set():
                return False
            if time.monotonic() - t0 > max_s:
                raise RetestError("waiting for the next sensor", f"Next was not pressed within {max_s:.0f} s")
        return True

    def _bag(self, p: dict, st) -> None:
        res = run_bag(self.source, self.disp, self.raw_dir, p.get("label", "check"), self._wait_next,
                      log=st.log, progress=getattr(st, "progress", None), stop=self.stop_event)
        # Agent loop: SENSE (the three gas rises) -> DECIDE (on-device) -> ACT (physical + message).
        t0 = time.perf_counter()
        feats = {f"{s}_d_peak": v for s, v in res.rises.items()}
        grade, rises = rules.quick_grade(feats)
        adv = agent.advise(grade, feats, p.get("label", "check"), use_llm=False)
        decide_ms = round((time.perf_counter() - t0) * 1000, 2)
        actions = self._act(grade, adv.text)
        out = {"grade": grade, "method": "rule", "rises_v": rises, "advice": adv.text,
               "capture_s": round(res.capture_s, 1), "decide_ms": decide_ms, "actions": actions}
        st.log(f"GRADE: {grade}")
        st.log(f"ADVICE: {adv.text}")
        st.log(f"ACT: {', '.join(actions)}")
        _annotate(Path(res.csv), out)
        st.finish("done", out)

    def _act(self, grade: str, advice: str) -> list[str]:
        """The agent's physical actions for a verdict (best effort, never raises)."""
        actions = []
        try:
            frame = display.icon(grade)
            if grade != "FRESH":
                # Alarm: flash the warning icon on the LED matrix before leaving it on.
                for _ in range(3):
                    self.disp.show(display.blank())
                    time.sleep(0.25)
                    self.disp.show(frame)
                    time.sleep(0.25)
            self.disp.show(frame)
            actions.append("led_alarm" if grade != "FRESH" else "led_ok")
        except Exception as e:  # noqa: BLE001
            print(f"act: LED failed: {e}", flush=True)
        if grade != "FRESH":
            try:
                n = notify.send(f"PGAS alert: {grade} - {advice}")
                actions.append("alert_sent" if n.get("sent") else "alert_queued")
            except Exception as e:  # noqa: BLE001
                print(f"act: alert failed: {e}", flush=True)
        return actions

    def _continuous(self, job: dict, st: jobs.Status, resume: ContinuousState | None) -> None:
        p = job.get("params", {})
        if resume:
            state = resume
            writer = CaptureWriter.resume(Path(state.csv))
            st.log(f"resumed recording to {Path(state.csv).name} ({writer.rows} rows so far)")
        else:
            from datetime import datetime

            started = datetime.now()
            writer = CaptureWriter(self.raw_dir, "continuous", p["label"], started)
            t0 = started.timestamp()
            until = t0 + p["hours"] * 3600 if p.get("hours") else None
            state = ContinuousState(job["id"], p["label"], str(writer.csv_path), t0, until)
            state.save(self.state_path)
            st.log(f"recording to {writer.csv_path.name} (one row per minute)")
        n = run_continuous(self.source, self.disp, writer, state.t0, self.stop_event, until=state.until,
                           log=st.log)
        writer.close(stopped=True)
        self.state_path.unlink(missing_ok=True)
        st.log(f"continuous capture finished: {writer.rows} rows ({n} this run)")
        st.finish("done", {"csv": Path(state.csv).name, "rows": writer.rows})

    def _selftest(self, st: jobs.Status, duration_s: int = 20) -> None:
        st.log(f"collecting {duration_s} s of readings...")
        self.disp.show(display.text3("T"))
        self.source.flush()
        readings, t0 = [], time.monotonic()
        while time.monotonic() - t0 < duration_s:
            r = self.source.read(1.0)
            if r is not None:
                readings.append(r)
        checks = selftest.evaluate(readings, time.monotonic() - t0)
        text = selftest.report(checks)
        for line in text.splitlines():
            st.log(line)
        ok = all(c.ok for c in checks)
        self.disp.show(display.icon("FRESH" if ok else "DO-NOT-SELL"))
        log_dir = self.data_dir / "selftest"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{time.strftime('%Y%m%dT%H%M%S')}.txt").write_text(text + "\n")
        st.finish("done" if ok else "failed", {"pass": ok, "report": text})

    def resume_if_needed(self) -> None:
        state = ContinuousState.load(self.state_path)
        if state is None or not Path(state.csv).exists():
            return
        self.busy.acquire()
        self.current = f"continuous job {state.job_id}"
        st = self._status(state.job_id + "-resumed", "continuous")
        job = {"id": state.job_id, "kind": "continuous", "params": {"label": state.label}}
        threading.Thread(target=self._run, args=(job, st, state), daemon=True).start()

    def loop(self, poll_s: float = 0.5) -> None:
        self.poll_once()
        time.sleep(poll_s)


def _annotate(csv_path: Path, result: dict) -> None:
    """Store the on-board result next to the capture (JSON sidecar)."""
    import json

    meta_path = csv_path.with_suffix(".json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta["onboard_result"] = {k: v for k, v in result.items() if k != "features"}
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
