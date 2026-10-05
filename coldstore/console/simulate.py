"""Deterministic simulation ticks."""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from coldstore.ns import control_line

from .http import Request, Response, json_response
from .runtime import Runtime

DEFAULT_TICKS = 5
MAX_TICKS = 100
START_TEMP = -18.0
TEMP_STEP = 0.4


@dataclass(frozen=True)
class Tick:
    """One simulated control step."""

    index: int
    temp: float
    load: float
    high: bool
    running: int
    total_stage: int
    defrosting: int
    due: int
    latched: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "temp": self.temp,
            "load": self.load,
            "high": self.high,
            "running": self.running,
            "total_stage": self.total_stage,
            "defrosting": self.defrosting,
            "due": self.due,
            "latched": self.latched,
        }


@dataclass(frozen=True)
class SimulationReport:
    """The full sequence plus closing counters."""

    ticks: list[Tick] = field(default_factory=list)
    final_audit_count: int = 0
    last_stage: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "ticks": [tick.as_dict() for tick in self.ticks],
            "final_audit_count": self.final_audit_count,
            "last_stage": self.last_stage,
        }


def run_simulation(rt: Runtime, request: Request) -> Response:
    """Run a bounded number of ticks so the console can be exercised offline."""

    ticks = request.int_field("ticks", DEFAULT_TICKS)
    if ticks <= 0:
        ticks = DEFAULT_TICKS
    if ticks > MAX_TICKS:
        ticks = MAX_TICKS

    base_at = int(time.time())
    steps: list[Tick] = []
    for index in range(ticks):
        value = round(START_TEMP + index * TEMP_STEP, 4)
        rt.temp.record(value, at=base_at + index * 60)
        entry = rt.load.estimate(value)
        steps.append(
            Tick(
                index=index,
                temp=value,
                load=entry.load,
                high=entry.high,
                running=rt.compressors.running_count(),
                total_stage=rt.compressors.total_stage(),
                defrosting=len(rt.defrost.defrosting()),
                due=len(rt.scheduler.due(rt.rooms)),
                latched=rt.ammonia.latched(),
            )
        )

    last_stage = control_line().last()
    report = SimulationReport(
        ticks=steps,
        final_audit_count=rt.auditor.count(),
        last_stage="" if last_stage is None else last_stage.value,
    )
    return json_response(report.as_dict())
