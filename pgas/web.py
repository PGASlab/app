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

Every public method swallows its own errors: it is called from the Bridge
thread and from job threads, which must never fail because of the dashboard.
"""

from __future__ import annotations

import collections
import math
import threading
import time
from typing import Any, Callable

from . import config

HISTORY_S = 300  # what the dashboard charts: the last 5 minutes at 1 Hz


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
                for k in ("grade", "advice", "error", "note", "retest", "step", "pass"):
                    v = result.get(k)
                    if v is not None:
                        msg[k] = v if isinstance(v, bool) else str(v)
            with self.lock:
                self.last_job = msg
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

    def finish(self, state: str, result=None) -> None:
        self._status.finish(state, result)
        try:
            self._feed.job_done(*self._ids(), state, result)
        except Exception:  # noqa: BLE001
            pass

    def __getattr__(self, name):
        return getattr(self._status, name)
