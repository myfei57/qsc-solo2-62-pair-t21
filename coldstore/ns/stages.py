"""Named stages of the refrigeration control line."""

from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    """A single step on the control line."""

    TEMP = "temp"
    AMMONIA = "ammonia"
    COMP = "comp"
    VALVE = "valve"
    DEFROST = "defrost"
    EVAP = "evap"
    INTERLOCK = "interlock"
    QUOTA = "quota"
    AUDIT = "audit"

    def __str__(self) -> str:
        return self.value
