"""Temperature driven defrost planner."""

from __future__ import annotations

from coldstore.room import RoomRegistry
from coldstore.store.epoch import load_float, save_float
from coldstore.store.store import Store

from .report import ScheduleEntry, ScheduleState

THRESHOLD_KEY = "schedule:temp-threshold"
DEFAULT_THRESHOLD = -12.0
DEFROST_BASE_SECONDS = 120
DEFROST_SECONDS_PER_DEGREE = 20


class Scheduler:
    """Orders defrost work from the warmest room down to the coldest."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def threshold(self) -> float:
        value, present = load_float(self._store, THRESHOLD_KEY)
        return value if present else DEFAULT_THRESHOLD

    def set_threshold(self, value: float) -> float:
        save_float(self._store, THRESHOLD_KEY, value)
        return value

    def due(self, rooms: RoomRegistry) -> list[str]:
        """Rooms at or above the temperature threshold, warmest first."""

        threshold = self.threshold()
        loaded = [room for room in rooms.rooms() if room.temp >= threshold]
        loaded.sort(key=lambda room: (-room.temp, room.id))
        return [room.id for room in loaded]

    def plan(self, rooms: RoomRegistry) -> list[ScheduleEntry]:
        """Number every room by temperature so the warmest defrosts first."""

        ordered = sorted(rooms.rooms(), key=lambda room: (-room.temp, room.id))
        return [
            ScheduleEntry(
                room_id=room.id,
                temp=room.temp,
                priority=index + 1,
                defrost_seconds=DEFROST_BASE_SECONDS + int(abs(room.temp) * DEFROST_SECONDS_PER_DEGREE),
            )
            for index, room in enumerate(ordered)
        ]

    def state(self, rooms: RoomRegistry) -> ScheduleState:
        return ScheduleState(
            threshold=self.threshold(),
            due=self.due(rooms),
            entries=self.plan(rooms),
        )

    def describe(self, rooms: RoomRegistry) -> str:
        state = self.state(rooms)
        return f"schedule threshold={state.threshold:.4f} due={len(state.due)}"
