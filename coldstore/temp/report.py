"""Temperature projections and validation rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateVerdict:
    """The rate of change of the last reading against the allowed window."""

    value: float
    rate: float
    window: float
    within: bool
    direction: str

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "rate": self.rate,
            "window": self.window,
            "within": self.within,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class TempState:
    """Latest reading, the current rate and the window it must stay inside."""

    value: float
    rate: float
    window: float
    within: bool
    samples: int

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "rate": self.rate,
            "window": self.window,
            "within": self.within,
            "samples": self.samples,
        }


def validate_temp(value: float) -> None:
    """Reject readings outside the supported probe range."""

    if value < -100:
        raise ValueError("temp is below the supported range")
    if value > 100:
        raise ValueError("temp exceeds the supported range")
