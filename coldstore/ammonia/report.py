"""Ammonia projections and validation rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AmmoniaVerdict:
    """A calibrated reading and the level it landed on."""

    ppm: float
    calibrated: float
    threshold: float
    level: str
    trip: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "ppm": self.ppm,
            "calibrated": self.calibrated,
            "threshold": self.threshold,
            "level": self.level,
            "trip": self.trip,
        }


@dataclass(frozen=True)
class AmmoniaState:
    """Last reading, the threshold and whether a trip is latched."""

    last: float
    threshold: float
    calibration: float
    latched: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "last": self.last,
            "threshold": self.threshold,
            "calibration": self.calibration,
            "latched": self.latched,
        }


def validate_ppm(value: float) -> None:
    """Reject readings outside the supported sensor range."""

    if value < 0:
        raise ValueError("ppm must be non-negative")
    if value > 1_000_000:
        raise ValueError("ppm exceeds the supported range")


def validate_threshold(value: float) -> None:
    """Reject thresholds outside the supported range."""

    if value <= 0:
        raise ValueError("threshold must be positive")
    if value > 1_000_000:
        raise ValueError("threshold exceeds the supported range")
