"""Scheduling projections and validation rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduleEntry:
    """One planned defrost with its position and duration."""

    room_id: str
    temp: float
    priority: int
    defrost_seconds: int

    def as_dict(self) -> dict[str, object]:
        return {
            "room_id": self.room_id,
            "temp": self.temp,
            "priority": self.priority,
            "defrost_seconds": self.defrost_seconds,
        }


@dataclass(frozen=True)
class ScheduleState:
    """Threshold, due rooms and the ordered plan."""

    threshold: float
    due: list[str]
    entries: list[ScheduleEntry]

    def as_dict(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "due": self.due,
            "entries": [entry.as_dict() for entry in self.entries],
        }


def validate_threshold(value: float) -> None:
    """Reject thresholds outside the supported temperature range."""

    if value < -100:
        raise ValueError("threshold is below the supported range")
    if value > 100:
        raise ValueError("threshold exceeds the supported range")
