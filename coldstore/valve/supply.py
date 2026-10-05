"""Supply valve sequencing.

Liquid must be available before a compressor is asked to run, so the valve is
persisted open first and only then is the compressor started. Stopping runs in
the opposite order, which keeps the machine from pulling against a closed
line.
"""

from __future__ import annotations

from coldstore.comp import Bank
from coldstore.store.store import Store

from .report import CLOSED, OPEN, SupplyState

VALVE_KEY_PREFIX = "valve:supply:"


class SupplyValve:
    """Coordinates supply valve position with the compressor bank."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def position(self, comp_id: str) -> str:
        value, present = self._store.get(f"{VALVE_KEY_PREFIX}{comp_id}")
        if not present:
            return CLOSED
        return OPEN if value == OPEN else CLOSED

    def is_open(self, comp_id: str) -> bool:
        return self.position(comp_id) == OPEN

    def open_valve(self, comp_id: str) -> str:
        self._store.put(f"{VALVE_KEY_PREFIX}{comp_id}", OPEN)
        return OPEN

    def close_valve(self, comp_id: str) -> str:
        self._store.put(f"{VALVE_KEY_PREFIX}{comp_id}", CLOSED)
        return CLOSED

    def opened_ids(self) -> list[str]:
        opened: list[str] = []
        for key in self._store.keys():
            if key.startswith(VALVE_KEY_PREFIX) and self._store.get(key)[0] == OPEN:
                opened.append(key[len(VALVE_KEY_PREFIX) :])
        return opened

    def start_with_supply(self, bank: Bank, comp_id: str) -> str:
        """Open the valve, then start the compressor behind it."""

        self.open_valve(comp_id)
        if not self.is_open(comp_id):
            raise ValueError(f"supply valve for {comp_id} did not open")
        bank.start(comp_id)
        return comp_id

    def stop_with_supply(self, bank: Bank, comp_id: str) -> str:
        """Stop the compressor, then close the valve."""

        bank.stop(comp_id)
        self.close_valve(comp_id)
        return comp_id

    def state(self) -> SupplyState:
        return SupplyState(opened=self.opened_ids())

    def describe(self) -> str:
        return f"supply valves_open={len(self.opened_ids())}"
