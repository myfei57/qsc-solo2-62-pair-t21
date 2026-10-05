"""Ammonia leak monitor.

Readings are scaled by the calibration factor before they are compared to the
trip threshold, so a drifting sensor does not silently widen the safety band.
Crossing the threshold latches a trip that only an explicit reset clears.
"""

from __future__ import annotations

from coldstore.store.epoch import load_float, save_float
from coldstore.store.store import Store

from .report import AmmoniaState, AmmoniaVerdict

THRESHOLD_KEY = "ammonia:threshold"
CALIBRATION_KEY = "ammonia:calibration"
LAST_KEY = "ammonia:last"
LATCH_KEY = "ammonia:latch"
DEFAULT_THRESHOLD = 25.0
DEFAULT_CALIBRATION = 1.0
WARN_FACTOR = 0.6


def level_for(ppm: float, threshold: float) -> str:
    """Classify a calibrated reading against the trip threshold."""

    if threshold <= 0:
        return "trip" if ppm > 0 else "ok"
    if ppm >= threshold:
        return "trip"
    if ppm >= threshold * WARN_FACTOR:
        return "warn"
    return "ok"


class Monitor:
    """Holds the calibrated threshold, the last reading and the latch."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def threshold(self) -> float:
        value, present = load_float(self._store, THRESHOLD_KEY)
        return value if present else DEFAULT_THRESHOLD

    def set_threshold(self, value: float) -> float:
        save_float(self._store, THRESHOLD_KEY, value)
        return value

    def calibration(self) -> float:
        value, present = load_float(self._store, CALIBRATION_KEY)
        return value if present else DEFAULT_CALIBRATION

    def calibrate(self, factor: float) -> float:
        if factor <= 0:
            raise ValueError("calibration factor must be positive")
        save_float(self._store, CALIBRATION_KEY, factor)
        return factor

    def calibrated(self, ppm: float) -> float:
        return ppm * self.calibration()

    def last(self) -> float:
        value, _ = load_float(self._store, LAST_KEY)
        return value

    def latched(self) -> bool:
        return self._store.get(LATCH_KEY)[1]

    def detect(self, ppm: float) -> AmmoniaVerdict:
        """Scale, classify and latch a reading when it crosses the threshold."""

        calibrated = self.calibrated(ppm)
        threshold = self.threshold()
        level = level_for(calibrated, threshold)
        trip = level == "trip"
        save_float(self._store, LAST_KEY, calibrated)
        if trip:
            self._store.put(LATCH_KEY, "true")
        return AmmoniaVerdict(
            ppm=ppm,
            calibrated=calibrated,
            threshold=threshold,
            level=level,
            trip=trip,
        )

    def reset(self) -> None:
        self._store.delete(LATCH_KEY)

    def state(self) -> AmmoniaState:
        return AmmoniaState(
            last=self.last(),
            threshold=self.threshold(),
            calibration=self.calibration(),
            latched=self.latched(),
        )

    def describe(self) -> str:
        state = self.state()
        return (
            f"ammonia last={state.last:.4f} threshold={state.threshold:.4f} "
            f"latched={state.latched}"
        )
