"""The set of cold rooms under one control console."""

from __future__ import annotations

import threading

from .report import RoomState, RoomView


class Room:
    """Mutable state of one cold room."""

    def __init__(
        self,
        room_id: str,
        zone: int,
        temp: float = 0.0,
        compressor: str = "",
        sensor: str = "",
    ) -> None:
        self.id = room_id
        self.zone = zone
        self.temp = temp
        self.compressor = compressor
        self.sensor = sensor
        self.defrosting = False

    def snapshot(self) -> dict[str, object]:
        return {
            "id": self.id,
            "zone": self.zone,
            "temp": self.temp,
            "compressor": self.compressor,
            "sensor": self.sensor,
            "defrosting": self.defrosting,
        }


class RoomRegistry:
    """Thread safe registry of cold rooms.

    Rooms are stored by identifier. Lookups that mutate a room run under the
    registry lock so concurrent console requests cannot interleave.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock = threading.RLock()

    def add_room(self, room_id: str, zone: int, temp: float = 0.0) -> Room:
        with self._lock:
            room = Room(room_id=room_id, zone=zone, temp=temp)
            self._rooms[room_id] = room
            return room

    def room(self, room_id: str) -> Room | None:
        with self._lock:
            return self._rooms.get(room_id)

    def rooms(self) -> list[Room]:
        with self._lock:
            return [self._rooms[key] for key in sorted(self._rooms)]

    def room_ids(self) -> list[str]:
        return [room.id for room in self.rooms()]

    def count(self) -> int:
        with self._lock:
            return len(self._rooms)

    def remove_room(self, room_id: str) -> None:
        with self._lock:
            if room_id not in self._rooms:
                raise ValueError(f"cold room {room_id} not found")
            del self._rooms[room_id]

    def set_temp(self, room_id: str, temp: float) -> None:
        with self._lock:
            self._require(room_id).temp = temp

    def set_defrosting(self, room_id: str, value: bool) -> None:
        with self._lock:
            self._require(room_id).defrosting = value

    def reset_defrosting(self) -> None:
        with self._lock:
            for room in self._rooms.values():
                room.defrosting = False

    def defrosting_ids(self) -> list[str]:
        return [room.id for room in self.rooms() if room.defrosting]

    def assign_compressor(self, room_id: str, compressor: str) -> None:
        with self._lock:
            self._require(room_id).compressor = compressor

    def assign_sensor(self, room_id: str, sensor: str) -> None:
        with self._lock:
            self._require(room_id).sensor = sensor

    def assignment(self, room_id: str) -> tuple[str, str, bool]:
        """Return the compressor and ammonia sensor bound to a room."""

        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return "", "", False
            return room.compressor, room.sensor, True

    def rooms_for_compressor(self, compressor: str) -> list[str]:
        return [
            room.id
            for room in self.rooms()
            if room.compressor and room.compressor == compressor
        ]

    def renumber(self, room_id: str, zone: int) -> None:
        with self._lock:
            self._require(room_id).zone = zone

    def mapping(self) -> dict[int, str]:
        """Zone to room identifier, rebuilt from the live registry."""

        with self._lock:
            return {room.zone: room_id for room_id, room in self._rooms.items()}

    def room_zone(self, room_id: str) -> tuple[int, bool]:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return 0, False
            return room.zone, True

    def temp(self, room_id: str) -> tuple[float, bool]:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return 0.0, False
            return room.temp, True

    def hottest(self) -> str:
        rooms = self.rooms()
        if not rooms:
            return ""
        return max(rooms, key=lambda room: (room.temp, room.id)).id

    def coldest(self) -> str:
        rooms = self.rooms()
        if not rooms:
            return ""
        return min(rooms, key=lambda room: (room.temp, room.id)).id

    def average_temp(self) -> float:
        rooms = self.rooms()
        if not rooms:
            return 0.0
        return sum(room.temp for room in rooms) / len(rooms)

    def unassigned(self) -> list[str]:
        return [room.id for room in self.rooms() if not room.compressor]

    def state(self) -> RoomState:
        rooms = self.rooms()
        return RoomState(
            rooms=[
                RoomView(
                    id=room.id,
                    zone=room.zone,
                    temp=room.temp,
                    compressor=room.compressor,
                    sensor=room.sensor,
                    defrosting=room.defrosting,
                )
                for room in rooms
            ],
            count=len(rooms),
            average_temp=self.average_temp(),
            hottest=self.hottest(),
        )

    def describe(self) -> str:
        state = self.state()
        return f"cold rooms={state.count} hottest={state.hottest or ''}"

    def _require(self, room_id: str) -> Room:
        room = self._rooms.get(room_id)
        if room is None:
            raise ValueError(f"cold room {room_id} not found")
        return room
