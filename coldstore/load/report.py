"""Cooling load projections and validation rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadEntry:
    """One room's load against the shared baseline."""

    temp: float
    baseline: float
    load: float
    high: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "temp": self.temp,
            "baseline": self.baseline,
            "load": self.load,
            "high": self.high,
        }


@dataclass(frozen=True)
class LoadState:
    """Baseline, coefficient and the per room load breakdown."""

    baseline: float
    coefficient: float
    total: float
    entries: list[LoadEntry]

    def as_dict(self) -> dict[str, object]:
        return {
            "baseline": self.baseline,
            "coefficient": self.coefficient,
            "total": self.total,
            "entries": [entry.as_dict() for entry in self.entries],
        }


def validate_baseline(value: float) -> None:
    """Reject baselines outside the supported range."""

    if value < -100:
        raise ValueError("baseline is below the supported range")
    if value > 100:
        raise ValueError("baseline exceeds the supported range")
