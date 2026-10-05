"""Runtime telemetry counters."""

from __future__ import annotations

from dataclasses import dataclass

from .runtime import Runtime


@dataclass(frozen=True)
class Telemetry:
    """A flat snapshot of the numbers an operator watches."""

    store_keys: int
    rooms: int
    defrosting: int
    average_temp: float
    compressors: int
    compressors_running: int
    total_stage: int
    max_stage: int
    load_ratio: float
    supply_open: int
    temp_value: float
    temp_rate: float
    temp_within: bool
    ammonia_last: float
    ammonia_latched: bool
    interlock_tripped: bool
    interlock_trips: int
    cold_primary: str
    cold_running: int
    evap_temperature: float
    evap_above: bool
    defrost_warmups: int
    cooling_load: float
    quota_value: float
    audit_entries: int
    schedule_due: int

    def as_dict(self) -> dict[str, object]:
        return {
            "store_keys": self.store_keys,
            "rooms": self.rooms,
            "defrosting": self.defrosting,
            "average_temp": self.average_temp,
            "compressors": self.compressors,
            "compressors_running": self.compressors_running,
            "total_stage": self.total_stage,
            "max_stage": self.max_stage,
            "load_ratio": self.load_ratio,
            "supply_open": self.supply_open,
            "temp_value": self.temp_value,
            "temp_rate": self.temp_rate,
            "temp_within": self.temp_within,
            "ammonia_last": self.ammonia_last,
            "ammonia_latched": self.ammonia_latched,
            "interlock_tripped": self.interlock_tripped,
            "interlock_trips": self.interlock_trips,
            "cold_primary": self.cold_primary,
            "cold_running": self.cold_running,
            "evap_temperature": self.evap_temperature,
            "evap_above": self.evap_above,
            "defrost_warmups": self.defrost_warmups,
            "cooling_load": self.cooling_load,
            "quota_value": self.quota_value,
            "audit_entries": self.audit_entries,
            "schedule_due": self.schedule_due,
        }


def collect(rt: Runtime) -> Telemetry:
    """Read every counter without mutating the control state."""

    temp = rt.temp.state()
    compressor_state = rt.compressors.state()
    return Telemetry(
        store_keys=rt.store.count(),
        rooms=rt.rooms.count(),
        defrosting=len(rt.defrost.defrosting()),
        average_temp=rt.rooms.average_temp(),
        compressors=rt.compressors.count(),
        compressors_running=compressor_state.running,
        total_stage=compressor_state.total_stage,
        max_stage=compressor_state.max_stage,
        load_ratio=compressor_state.load_ratio,
        supply_open=len(rt.supply.opened_ids()),
        temp_value=temp.value,
        temp_rate=temp.rate,
        temp_within=temp.within,
        ammonia_last=rt.ammonia.last(),
        ammonia_latched=rt.ammonia.latched(),
        interlock_tripped=rt.interlock.is_tripped(),
        interlock_trips=rt.interlock.count(),
        cold_primary=rt.cold_fans.primary(),
        cold_running=len(rt.cold_fans.running_ids()),
        evap_temperature=rt.evap.temperature(),
        evap_above=rt.evap.above_baseline(),
        defrost_warmups=rt.defrost.warmup_count(),
        cooling_load=rt.load.total(rt.rooms),
        quota_value=rt.accumulator.value(),
        audit_entries=rt.auditor.count(),
        schedule_due=len(rt.scheduler.due(rt.rooms)),
    )
