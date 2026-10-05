"""Full component snapshot exposed by the console."""

from __future__ import annotations

from coldstore.ns import control_line
from coldstore.store import store_state

from .runtime import Runtime


def collect(rt: Runtime) -> dict[str, object]:
    """Combine every component projection into one document."""

    return {
        "pipeline": [step.as_dict() for step in control_line().steps()],
        "store": store_state(rt.store).as_dict(),
        "rooms": rt.rooms.state().as_dict(),
        "compressors": rt.compressors.state().as_dict(),
        "supply": rt.supply.state().as_dict(),
        "temp": rt.temp.state().as_dict(),
        "ammonia": rt.ammonia.state().as_dict(),
        "interlock": rt.interlock.state().as_dict(),
        "cold_fans": rt.cold_fans.state().as_dict(),
        "evap": rt.evap.state().as_dict(),
        "defrost": rt.defrost.state().as_dict(),
        "load": rt.load.state(rt.rooms).as_dict(),
        "quota": rt.accumulator.state().as_dict(),
        "audit": rt.auditor.state().as_dict(),
        "schedule": rt.scheduler.state(rt.rooms).as_dict(),
    }
