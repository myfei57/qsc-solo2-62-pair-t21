"""Fan projections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FanView:
    """Read only copy of one fan."""

    id: str
    role: str
    running: bool
    faulted: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "role": self.role,
            "running": self.running,
            "faulted": self.faulted,
        }


@dataclass(frozen=True)
class FanState:
    """Every fan plus the current primary and active unit."""

    fans: list[FanView]
    primary: str
    active: str
    count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "fans": [fan.as_dict() for fan in self.fans],
            "primary": self.primary,
            "active": self.active,
            "count": self.count,
        }
