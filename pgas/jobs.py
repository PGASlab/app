"""File-based job queue between the CLI and the running App Lab app.

The app's Python runs in a Docker container that owns the Bridge to the MCU.
The app folder is mounted into the container (/app) and is also visible on the
board (~/ArduinoApps/pgas), so the CLI and the app talk through files:

    data/jobs/pending/<id>.json   written by the CLI
    data/jobs/status/<id>.json    written by the app: state, log lines, result

Standard library only: the CLI also runs on the board's host Python.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

KINDS = ("hood", "continuous", "selftest", "stop", "bag")
FINAL = ("done", "failed", "rejected")


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)


def submit(jobs_dir: Path, kind: str, **params) -> str:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    job_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    _write_atomic(Path(jobs_dir) / "pending" / f"{job_id}.json",
                  {"id": job_id, "kind": kind, "params": params, "created": time.time()})
    return job_id


def claim(jobs_dir: Path) -> dict | None:
    """Take the oldest pending job (app side)."""
    pend = Path(jobs_dir) / "pending"
    for p in sorted(pend.glob("*.json")):
        try:
            job = json.loads(p.read_text())
            p.unlink()
            return job
        except (OSError, ValueError):
            continue
    return None


class Status:
    def __init__(self, jobs_dir: Path, job_id: str, kind: str):
        self.path = Path(jobs_dir) / "status" / f"{job_id}.json"
        self.data = {"id": job_id, "kind": kind, "state": "running", "lines": [], "result": None,
                     "updated": time.time()}
        self._save()

    def _save(self) -> None:
        self.data["updated"] = time.time()
        _write_atomic(self.path, self.data)

    def log(self, line: str) -> None:
        print(f"[{self.data['id']}] {line}", flush=True)
        self.data["lines"].append(f"{datetime.now():%H:%M:%S} {line}")
        self.data["lines"] = self.data["lines"][-500:]
        self._save()

    def finish(self, state: str, result=None) -> None:
        self.data["state"] = state
        self.data["result"] = result
        self._save()


def read_status(jobs_dir: Path, job_id: str) -> dict | None:
    try:
        return json.loads((Path(jobs_dir) / "status" / f"{job_id}.json").read_text())
    except (OSError, ValueError):
        return None


def follow(jobs_dir: Path, job_id: str, detach_when=None, start_timeout_s: float = 20.0,
           poll_s: float = 0.5, out=print) -> dict:
    """Print status lines as they appear until the job ends (CLI side)."""
    t0 = time.time()
    shown = 0
    while True:
        st = read_status(jobs_dir, job_id)
        if st is None:
            if time.time() - t0 > start_timeout_s:
                raise TimeoutError(
                    "the PGAS app did not pick up the job. Is it running?  "
                    "arduino-app-cli app start user:pgas")
            time.sleep(poll_s)
            continue
        for line in st["lines"][shown:]:
            out(line)
        shown = len(st["lines"])
        if st["state"] in FINAL or (detach_when and detach_when(st)):
            return st
        time.sleep(poll_s)
