"""Evaporative condenser temperature baseline.

The condenser is held near a stored baseline. When the reading climbs above
that baseline the duty fan is the active primary unit, so the runtime can call
for a standby changeover before the head pressure runs away.
"""

from __future__ import annotations

from coldstore.fan import FanSet
from coldstore.store.epoch import load_float, save_float
from coldstore.store.store import Store

from .report import CondenserState

BASELINE_KEY = "evap:baseline"
TEMP_KEY = "evap:temperature"
DEFAULT_BASELINE = 32.0


class Condenser:
    """Holds the condenser temperature and the baseline it is compared to."""

    def __init__(self, store: Store, fans: FanSet) -> None:
        self._store = store
        self._fans = fans

    def baseline(self) -> float:
        value, present = load_float(self._store, BASELINE_KEY)
        return value if present else DEFAULT_BASELINE

    def set_baseline(self, value: float) -> float:
        save_float(self._store, BASELINE_KEY, value)
        return value

    def temperature(self) -> float:
        value, _ = load_float(self._store, TEMP_KEY)
        return value

    def set_temperature(self, value: float) -> float:
        save_float(self._store, TEMP_KEY, value)
        return value

    def above_baseline(self) -> bool:
        return self.temperature() > self.baseline()

    def duty(self) -> str:
        """Active evaporative fan, or an empty string when none is running."""

        return self._fans.active()

    def switch_to_standby(self, fan_id: str) -> str:
        """Promote one fan and stop the unit that was running before."""

        previous = self._fans.active()
        if previous and previous != fan_id:
            self._fans.stop(previous)
        primary = self._fans.switch_over(fan_id)
        self._fans.start(primary)
        return primary

    def state(self) -> CondenserState:
        return CondenserState(
            temperature=self.temperature(),
            baseline=self.baseline(),
            above_baseline=self.above_baseline(),
            duty=self.duty(),
        )

    def describe(self) -> str:
        state = self.state()
        return (
            f"evap temperature={state.temperature:.4f} baseline={state.baseline:.4f} "
            f"duty={state.duty or ''}"
        )
