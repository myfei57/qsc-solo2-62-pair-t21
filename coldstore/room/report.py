"""Cold room projections and validation rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoomView:
    """Read only copy of one cold room."""

    id: str
    zone: int
    temp: float
    compressor: str
    sensor: str
    defrosting: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "zone": self.zone,
            "temp": self.temp,
            "compressor": self.compressor,
            "sensor": self.sensor,
            "defrosting": self.defrosting,
        }


@dataclass(frozen=True)
class RoomState:
    """Every room plus the aggregate readings the operator watches."""

    rooms: list[RoomView]
    count: int
    average_temp: float
    hottest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "rooms": [room.as_dict() for room in self.rooms],
            "count": self.count,
            "average_temp": self.average_temp,
            "hottest": self.hottest,
        }


def validate_zone(zone: int) -> None:
    """Reject zone numbers outside the supported range."""

    if zone < 0:
        raise ValueError("zone must be non-negative")
    if zone > 100_000:
        raise ValueError("zone exceeds the supported range")
