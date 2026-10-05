"""Ordered control line and the action performed at each stage."""

from __future__ import annotations

from dataclasses import dataclass

from .stages import Stage

STAGE_ACTIONS: dict[Stage, str] = {
    Stage.TEMP: "sample room temperature",
    Stage.AMMONIA: "judge ammonia level",
    Stage.COMP: "stage compressors",
    Stage.VALVE: "open the supply valve",
    Stage.DEFROST: "run defrost",
    Stage.EVAP: "hold the condenser",
    Stage.INTERLOCK: "latch the interlock",
    Stage.QUOTA: "meter runtime",
    Stage.AUDIT: "record audit",
}


@dataclass(frozen=True)
class Step:
    """A stage paired with the action the operator performs there."""

    stage: Stage
    action: str

    def as_dict(self) -> dict[str, str]:
        return {"stage": self.stage.value, "action": self.action}


@dataclass(frozen=True)
class Pipeline:
    """An ordered collection of stages."""

    name: str
    stages: tuple[Stage, ...]

    def index_of(self, stage: Stage) -> int:
        for index, candidate in enumerate(self.stages):
            if candidate is stage or candidate == stage:
                return index
        return -1

    def before(self, first: Stage, second: Stage) -> bool:
        first_index = self.index_of(first)
        second_index = self.index_of(second)
        return first_index >= 0 and second_index >= 0 and first_index < second_index

    def steps(self) -> list[Step]:
        return [Step(stage=stage, action=STAGE_ACTIONS.get(stage, "")) for stage in self.stages]

    def describe(self) -> str:
        return f"pipeline {self.name} has {len(self.stages)} stages"

    def last(self) -> Stage | None:
        if not self.stages:
            return None
        return self.stages[-1]

    def count(self) -> int:
        return len(self.stages)

    def contains(self, stage: Stage) -> bool:
        return self.index_of(stage) >= 0


def control_line() -> Pipeline:
    """Return the canonical ordering of the control stages."""

    return Pipeline(
        name="control",
        stages=(
            Stage.TEMP,
            Stage.AMMONIA,
            Stage.COMP,
            Stage.VALVE,
            Stage.DEFROST,
            Stage.EVAP,
            Stage.INTERLOCK,
            Stage.QUOTA,
            Stage.AUDIT,
        ),
    )
