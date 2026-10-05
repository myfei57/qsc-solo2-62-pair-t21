"""Defrost projections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefrostState:
    """Queued commands, warm up records and the rooms still defrosting."""

    commands: list[str]
    warmups: list[str]
    defrosting: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "commands": self.commands,
            "warmups": self.warmups,
            "defrosting": self.defrosting,
        }
