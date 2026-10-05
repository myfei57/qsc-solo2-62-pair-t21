"""Room temperature collection guarded by a rate window.

A cold room is judged by how fast its temperature moves, not only by where it
lands: a slow drift inside the window is acceptable, while a fast swing trips
the verdict so the compressor stage and defrost logic react before the goods
are damaged.
"""

from __future__ import annotations

import json
import time

from coldstore.store.epoch import load_float, save_float
from coldstore.store.store import Store

from .report import RateVerdict, TempState
from .sensor import Reading

READINGS_KEY = "temp:readings"
WINDOW_KEY = "temp:rate-window"
TEMP_KEY = "temp:last"
DEFAULT_WINDOW = 0.5
MAX_WINDOW = 100.0
MAX_SAMPLES = 64


class Collector:
    """Keeps a short history of readings and judges the closing rate."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def window(self) -> float:
        value, present = load_float(self._store, WINDOW_KEY)
        if not present or value <= 0:
            return DEFAULT_WINDOW
        return min(value, MAX_WINDOW)

    def set_window(self, value: float) -> float:
        if value <= 0:
            raise ValueError("window must be positive")
        if value > MAX_WINDOW:
            raise ValueError("window exceeds the supported range")
        save_float(self._store, WINDOW_KEY, value)
        return value

    def readings(self) -> list[Reading]:
        raw, present = self._store.get(READINGS_KEY)
        if not present:
            return []
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        if not isinstance(parsed, list):
            return []
        readings: list[Reading] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                readings.append(
                    Reading(value=float(item.get("value", 0.0)), at=int(item.get("at", 0)))
                )
            except (TypeError, ValueError):
                continue
        return readings

    def _save(self, readings: list[Reading]) -> None:
        self._store.put(READINGS_KEY, json.dumps([reading.as_dict() for reading in readings]))

    def current(self) -> float:
        value, present = load_float(self._store, TEMP_KEY)
        if present:
            return value
        readings = self.readings()
        if readings:
            return readings[-1].value
        return 0.0

    def rate(self) -> float:
        """Degrees per second between the two most recent readings."""

        readings = self.readings()
        if len(readings) < 2:
            return 0.0
        previous = readings[-2]
        latest = readings[-1]
        elapsed = latest.at - previous.at
        if elapsed <= 0:
            return 0.0
        return (latest.value - previous.value) / elapsed

    def within_window(self) -> bool:
        return abs(self.rate()) <= self.window()

    def direction(self) -> str:
        rate = self.rate()
        if rate > 0:
            return "rising"
        if rate < 0:
            return "falling"
        return "steady"

    def record(self, value: float, at: int | None = None) -> RateVerdict:
        """Append a reading and evaluate the rate against the window."""

        reading = Reading(value=float(value), at=int(at) if at is not None else int(time.time()))
        readings = self.readings()
        readings.append(reading)
        readings = readings[-MAX_SAMPLES:]
        self._save(readings)
        save_float(self._store, TEMP_KEY, reading.value)
        return self.verdict()

    def verdict(self) -> RateVerdict:
        rate = self.rate()
        window = self.window()
        return RateVerdict(
            value=self.current(),
            rate=rate,
            window=window,
            within=abs(rate) <= window,
            direction=self.direction(),
        )

    def reset(self) -> None:
        self._store.delete(READINGS_KEY)

    def state(self) -> TempState:
        verdict = self.verdict()
        return TempState(
            value=verdict.value,
            rate=verdict.rate,
            window=verdict.window,
            within=verdict.within,
            samples=len(self.readings()),
        )

    def describe(self) -> str:
        state = self.state()
        return (
            f"temp value={state.value:.4f} rate={state.rate:.4f} "
            f"window={state.window:.4f} within={state.within}"
        )
