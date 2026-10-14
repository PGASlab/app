"""Mock hardware for tests: a 1 Hz reading source that never sleeps."""

from __future__ import annotations

import math

from pgas.session import Reading


class MockSource:
    """Yields readings at simulated 1 s steps.

    `profile(i)` returns (a0, a1, a2) raw counts for step i; DHT values fixed
    unless `dht_fail` is set.
    """

    def __init__(self, profile=None, t0: float = 1_000_000.0, dht_fail: bool = False,
                 limit: int | None = None, step: float = 1.0, stop_when_done=None):
        self.profile = profile or (lambda i: (3000.0, 2500.0, 2800.0))
        self.stop_when_done = stop_when_done  # threading.Event set once `limit` is reached
        self.t0, self.i, self.dht_fail, self.limit, self.step = t0, 0, dht_fail, limit, step

    def read(self, timeout: float):
        if self.limit is not None and self.i >= self.limit:
            if self.stop_when_done is not None:
                self.stop_when_done.set()
            return None
        a0, a1, a2 = self.profile(self.i)
        r = Reading(self.t0 + self.i * self.step, a0, a1, a2,
                    None if self.dht_fail else 26.5, None if self.dht_fail else 65.0)
        self.i += 1
        return r

    def flush(self):
        pass


def hood_profile(rise: float, expose_from: int = 35, expose_to: int = 95):
    """Flat baseline, rise while the hood is on, decay after."""
    def f(i):
        if i < expose_from:
            k = 0.0
        elif i < expose_to:
            k = 1 - math.exp(-(i - expose_from) / 10)
        else:
            k = (1 - math.exp(-(expose_to - expose_from) / 10)) * math.exp(-(i - expose_to) / 5)
        return (3000 + rise * k, 2500 + rise * k, 2800 + rise * k)
    return f
