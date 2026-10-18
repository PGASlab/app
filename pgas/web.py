"""Live feed for the Wi-Fi dashboard (app/assets/index.html).

The App Lab `arduino:web_ui` brick serves app/assets on port 7000 and pushes
Socket.IO messages to the browser with `send_message(event, payload)`.
`LiveFeed` turns each 1 Hz Bridge sample into a small JSON payload and sends
it through any object that has such a `send_message` method, so this module
imports (and is tested) without the arduino package.

Events sent to the browser:
    pgas_sample   one reading (see `LiveFeed.sample`)
    pgas_history  the last few minutes of readings, sent to a client on connect
    pgas_job      a job log line or the end of a job (grade / advice / error)
    pgas_command_reply  the answer to a pgas_command from that browser

Events received from the browser (see `command`):
    pgas_command  {"action": "check"}: one bag test (each sensor in turn, labelled
                  "check", not used for training); {"action": "next"}: the
                  next sensor is ready; {"action": "hood", "food": "...", "state": "fresh"}
                  for a labelled capture; {"action": "selftest"} / {"action": "stop"}

Every public method swallows its own errors: it is called from the Bridge
thread and from job threads, which must never fail because of the dashboard.
"""

from __future__ import annotations

import collections
import math
import re
import threading
import time
from typing import Any, Callable

from . import config, jobs

HISTORY_S = 300  # what the dashboard charts: the last 5 minutes at 1 Hz

# Hood label = <state>_<food>. fresh / spoiling / spoiled / swill map to grades
# for training (pgas/labeling.py); "test" captures are recorded but not used.
STATES = ("fresh", "spoiling", "spoiled", "swill", "test")
_FOOD = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
FOOD_MAX = 40


def _volts(raw: float) -> float | None:
    try:
        v = config.adc_to_sensor_volts(float(raw))
    except (TypeError, ValueError):
        return None
    return round(v, 3) if math.isfinite(v) else None


def _num(x: Any, nd: int = 1) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def _raw(x: Any) -> float | None:
    v = _num(x, 1)
    if v is not None and v == int(v):
        return int(v)
    return v


class LiveFeed:
    def __init__(self, sink, clock: Callable[[], float] = time.time, history_s: int = HISTORY_S):
        self.sink = sink
        self.clock = clock
        self.history: collections.deque[dict] = collections.deque(maxlen=max(1, int(history_s)))
        self.last_job: dict | None = None
        self.lock = threading.Lock()
        self.errors = 0

    def _send(self, event: str, payload, room: str | None = None) -> None:
        try:
            if room is None:
                self.sink.send_message(event, payload)
            else:
                self.sink.send_message(event, payload, room=room)
        except Exception as e:  # noqa: BLE001 - the dashboard is best effort
            self.errors += 1
            if self.errors <= 3 or self.errors % 600 == 0:
                print(f"dashboard send failed ({self.errors}x): {e}", flush=True)

    # Called from Runtime.on_sample (Bridge thread): build, remember, send.
    def sample(self, a0, a1, a2, temp_c, rh_pct, dht_ok=1, job: str | None = None) -> dict | None:
        try:
            ok = bool(dht_ok)
            payload = {
                "ts": round(self.clock(), 3),
                "mq135_v": _volts(a0),
                "mq3_v": _volts(a1),
                "mq2_v": _volts(a2),
                "raw": [_raw(a0), _raw(a1), _raw(a2)],
                "temp_c": _num(temp_c) if ok else None,
                "rh_pct": _num(rh_pct) if ok else None,
                "dht_ok": ok,
                "job": str(job) if job else None,
            }
            with self.lock:
                self.history.append(payload)
        except Exception as e:  # noqa: BLE001
            self.errors += 1
            print(f"dashboard sample dropped: {e}", flush=True)
            return None
        self._send("pgas_sample", payload)
        return payload

    def job_line(self, job_id: str, kind: str, line: str) -> None:
        try:
            msg = {"ts": round(self.clock(), 3), "id": str(job_id), "kind": str(kind),
                   "state": "running", "line": str(line)}
        except Exception:  # noqa: BLE001
            return
        self._send("pgas_job", msg)

    def job_done(self, job_id: str, kind: str, state: str, result=None) -> None:
        try:
            msg = {"ts": round(self.clock(), 3), "id": str(job_id), "kind": str(kind),
                   "state": str(state)}
            if isinstance(result, dict):
                # Only small, JSON-safe fields: a result can hold numpy features.
                for k in ("grade", "advice", "error", "note", "retest", "step", "pass", "method"):
                    v = result.get(k)
                    if v is not None:
                        msg[k] = v if isinstance(v, bool) else str(v)
                rises = result.get("rises_v")
                if isinstance(rises, dict):
                    msg["rises_v"] = {str(k): _num(v, 3) for k, v in rises.items()}
            with self.lock:
                self.last_job = msg
        except Exception:  # noqa: BLE001
            return
        self._send("pgas_job", msg)

    def job_progress(self, job_id: str, kind: str, phase: str, i: int, n: int) -> None:
        try:
            msg = {"ts": round(self.clock(), 3), "id": str(job_id), "kind": str(kind),
                   "state": "running", "phase": str(phase), "i": int(i), "n": int(n)}
        except Exception:  # noqa: BLE001
            return
        self._send("pgas_job", msg)

    # web_ui.on_connect callback: give a new browser the recent chart history.
    def on_connect(self, sid: str) -> None:
        try:
            with self.lock:
                payload = {"samples": list(self.history), "last_job": self.last_job}
        except Exception:  # noqa: BLE001
            return
        self._send("pgas_history", payload, room=sid)

    def reply(self, sid, payload: dict) -> None:
        """Answer one browser (or all of them when the sid is unknown)."""
        self._send("pgas_command_reply", payload, room=sid if isinstance(sid, str) else None)


def command(jobs_dir, data, on_next=None) -> dict:
    """Handle a pgas_command from the dashboard by queueing a job.

    The job goes through the same file queue as `python -m pgas.capture`, so a
    test started from a phone runs exactly like one started from the CLI.
    Returns the reply for the browser; never raises.
    """
    try:
        d = data if isinstance(data, dict) else {}
        action = str(d.get("action", ""))
        if action == "hood":
            state = str(d.get("state", "")).strip().lower()
            food = re.sub(r"[\s-]+", "_", str(d.get("food", "")).strip().lower()).strip("_")
            if state not in STATES:
                return {"ok": False, "action": action, "error": "bad_state"}
            if not food or len(food) > FOOD_MAX or not _FOOD.match(food):
                return {"ok": False, "action": action, "error": "bad_food"}
            label = f"{state}_{food}"
            return {"ok": True, "action": action, "label": label,
                    "id": jobs.submit(jobs_dir, "hood", label=label)}
        if action == "check":
            # One sensor at a time in a small bag (pgas.session.run_bag).
            return {"ok": True, "action": action, "label": "check",
                    "id": jobs.submit(jobs_dir, "bag", label="check")}
        if action == "next":
            if on_next is None:
                return {"ok": False, "action": action, "error": "not_running"}
            on_next()
            return {"ok": True, "action": action}
        if action in ("selftest", "stop"):
            return {"ok": True, "action": action, "id": jobs.submit(jobs_dir, action)}
        return {"ok": False, "action": action, "error": "bad_action"}
    except Exception as e:  # noqa: BLE001 - reply with the error instead of crashing the handler
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


class FeedStatus:
    """Wraps a jobs.Status so job log lines and the result also reach the feed."""

    def __init__(self, status, feed: LiveFeed):
        self._status = status
        self._feed = feed

    def _ids(self) -> tuple[str, str]:
        d = getattr(self._status, "data", {}) or {}
        return d.get("id", "?"), d.get("kind", "?")

    def log(self, line: str) -> None:
        self._status.log(line)
        try:
            self._feed.job_line(*self._ids(), line)
        except Exception:  # noqa: BLE001
            pass

    def progress(self, phase: str, i: int, n: int) -> None:
        try:
            self._feed.job_progress(*self._ids(), phase, i, n)
        except Exception:  # noqa: BLE001
            pass

    def finish(self, state: str, result=None) -> None:
        self._status.finish(state, result)
        try:
            self._feed.job_done(*self._ids(), state, result)
        except Exception:  # noqa: BLE001
            pass

    def __getattr__(self, name):
        return getattr(self._status, name)
