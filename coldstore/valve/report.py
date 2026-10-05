"""Supply valve projections and validation rules."""

from __future__ import annotations

from dataclasses import dataclass

OPEN = "open"
CLOSED = "closed"


@dataclass(frozen=True)
class SupplyState:
    """Compressors whose supply valve is currently open."""

    opened: list[str]

    def as_dict(self) -> dict[str, object]:
        return {"opened": self.opened}


def validate_valve(value: str) -> None:
    """Reject valve positions the console cannot represent."""

    if value not in (OPEN, CLOSED):
        raise ValueError("valve position must be open or closed")
