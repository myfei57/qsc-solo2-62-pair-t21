"""Latched safety interlock.

An interlock trip is sticky: once a reason is recorded the latch stays set
until an operator explicitly resets it. That keeps a transient ammonia reading
from quietly letting the compressors restart.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass

from coldstore.store.commands import append_command, clear_commands, load_commands
from coldstore.store.store import Store

from .report import InterlockState

TRIPS_KEY = "interlock:trips"
LATCH_KEY = "interlock:latch"
REASON_KEY = "interlock:reason"


@dataclass(frozen=True)
class Trip:
    """One recorded interlock trip."""

    id: str
    time: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "time": self.time, "reason": self.reason}


class Interlock:
    """Records trips and holds the latch state."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def trip(self, reason: str) -> Trip:
        entry = Trip(
            id=uuid.uuid4().hex,
            time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            reason=reason,
        )
        append_command(self._store, TRIPS_KEY, json.dumps(entry.as_dict(), ensure_ascii=False))
        self._store.put(LATCH_KEY, "true")
        self._store.put(REASON_KEY, reason)
        return entry

    def reset(self) -> None:
        self._store.delete(LATCH_KEY)
        self._store.delete(REASON_KEY)

    def is_tripped(self) -> bool:
        return self._store.get(LATCH_KEY)[1]

    def reason(self) -> str:
        value, present = self._store.get(REASON_KEY)
        return value if present else ""

    def trips(self) -> list[Trip]:
        trips: list[Trip] = []
        for item in load_commands(self._store, TRIPS_KEY):
            try:
                payload = json.loads(item)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            trips.append(
                Trip(
                    id=str(payload.get("id", "")),
                    time=str(payload.get("time", "")),
                    reason=str(payload.get("reason", "")),
                )
            )
        return trips

    def last_trip(self) -> Trip | None:
        trips = self.trips()
        if not trips:
            return None
        return trips[-1]

    def count(self) -> int:
        return len(self.trips())

    def clear_log(self) -> None:
        clear_commands(self._store, TRIPS_KEY)

    def state(self) -> InterlockState:
        trips = self.trips()
        return InterlockState(
            tripped=self.is_tripped(),
            reason=self.reason(),
            trips=[trip.as_dict() for trip in trips],
            count=len(trips),
        )

    def describe(self) -> str:
        state = self.state()
        return f"interlock tripped={state.tripped} trips={state.count}"
