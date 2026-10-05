"""Interlock projections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InterlockState:
    """Latch state together with the recorded trip log."""

    tripped: bool
    reason: str
    trips: list[dict[str, str]]
    count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "tripped": self.tripped,
            "reason": self.reason,
            "trips": self.trips,
            "count": self.count,
        }
