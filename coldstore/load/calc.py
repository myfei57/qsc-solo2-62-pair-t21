"""Cooling load arithmetic.

The load follows the gap between a room temperature and the stored baseline,
scaled by a coefficient. Batch estimation lets the operator size a pull down
before the compressors are staged.
"""

from __future__ import annotations

from coldstore.room import RoomRegistry
from coldstore.store.epoch import load_float, save_float
from coldstore.store.store import Store

from .report import LoadEntry, LoadState

BASELINE_KEY = "load:baseline"
COEFFICIENT_KEY = "load:coefficient"
DEFAULT_BASELINE = -18.0
DEFAULT_COEFFICIENT = 1.5
HIGH_LOAD = 6.0


def compute_load(temp: float, baseline: float, coefficient: float) -> float:
    """Load implied by a temperature gap, floored at zero."""

    load = (temp - baseline) * coefficient
    return load if load > 0 else 0.0


class LoadCalculator:
    """Estimates cooling load against the stored baseline."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def baseline(self) -> float:
        value, present = load_float(self._store, BASELINE_KEY)
        return value if present else DEFAULT_BASELINE

    def set_baseline(self, value: float) -> float:
        save_float(self._store, BASELINE_KEY, value)
        return value

    def coefficient(self) -> float:
        value, present = load_float(self._store, COEFFICIENT_KEY)
        return value if present else DEFAULT_COEFFICIENT

    def set_coefficient(self, value: float) -> float:
        if value <= 0:
            raise ValueError("coefficient must be positive")
        save_float(self._store, COEFFICIENT_KEY, value)
        return value

    def load_for(self, temp: float) -> float:
        return compute_load(temp, self.baseline(), self.coefficient())

    def is_high(self, temp: float) -> bool:
        return self.load_for(temp) >= HIGH_LOAD

    def estimate(self, temp: float) -> LoadEntry:
        load = self.load_for(temp)
        return LoadEntry(temp=temp, baseline=self.baseline(), load=load, high=load >= HIGH_LOAD)

    def total(self, rooms: RoomRegistry) -> float:
        return sum(self.load_for(room.temp) for room in rooms.rooms())

    def state(self, rooms: RoomRegistry) -> LoadState:
        entries = [self.estimate(room.temp) for room in rooms.rooms()]
        return LoadState(
            baseline=self.baseline(),
            coefficient=self.coefficient(),
            total=sum(entry.load for entry in entries),
            entries=entries,
        )

    def describe(self, rooms: RoomRegistry) -> str:
        state = self.state(rooms)
        return (
            f"load baseline={state.baseline:.4f} total={state.total:.4f} "
            f"rooms={len(state.entries)}"
        )
