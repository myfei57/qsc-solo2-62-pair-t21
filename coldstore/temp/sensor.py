"""Raw temperature readings captured at a room probe."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    """A single room temperature observation with its timestamp."""

    value: float
    at: int

    def as_dict(self) -> dict[str, object]:
        return {"value": self.value, "at": self.at}
