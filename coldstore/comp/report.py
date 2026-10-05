"""Compressor projections and validation rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompressorView:
    """Read only copy of one compressor."""

    id: str
    stages: int
    stage: int
    running: bool
    reserved_by: str

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "stages": self.stages,
            "stage": self.stage,
            "running": self.running,
            "reserved_by": self.reserved_by,
        }


@dataclass(frozen=True)
class BankState:
    """The compressor bank and its aggregate loading."""

    compressors: list[CompressorView]
    running: int
    total_stage: int
    max_stage: int
    load_ratio: float

    def as_dict(self) -> dict[str, object]:
        return {
            "compressors": [compressor.as_dict() for compressor in self.compressors],
            "running": self.running,
            "total_stage": self.total_stage,
            "max_stage": self.max_stage,
            "load_ratio": self.load_ratio,
        }


def validate_stage(stage: int, stages: int = 8) -> None:
    """Reject stages outside the supported range."""

    if stage < 0:
        raise ValueError("stage must be non-negative")
    if stage > stages:
        raise ValueError("stage exceeds the supported range")
