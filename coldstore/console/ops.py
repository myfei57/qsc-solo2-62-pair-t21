"""Operator counters projected from the shared telemetry caliber."""

from __future__ import annotations

from dataclasses import dataclass

from .runtime import Runtime
from .telemetry import collect as collect_telemetry


@dataclass(frozen=True)
class OpsCounters:
    """Small set of counters shown on the operator page.

    Every field is a projection of the telemetry snapshot so the panel,
    the telemetry endpoint and the exports always agree.
    """

    store_keys: int
    rooms: int
    compressors: int
    compressors_running: int
    supply_open: int
    audit_entries: int
    requests: int
    request_errors: int

    def as_dict(self) -> dict[str, object]:
        return {
            "store_keys": self.store_keys,
            "rooms": self.rooms,
            "compressors": self.compressors,
            "compressors_running": self.compressors_running,
            "supply_open": self.supply_open,
            "audit_entries": self.audit_entries,
            "requests": self.requests,
            "request_errors": self.request_errors,
        }


def collect(rt: Runtime) -> OpsCounters:
    telemetry = collect_telemetry(rt)
    return OpsCounters(
        store_keys=telemetry.store_keys,
        rooms=telemetry.rooms,
        compressors=telemetry.compressors,
        compressors_running=telemetry.compressors_running,
        supply_open=telemetry.supply_open,
        audit_entries=telemetry.audit_entries,
        requests=telemetry.requests,
        request_errors=telemetry.request_errors,
    )


def reset_store(rt: Runtime) -> dict[str, object]:
    """Clear every persisted key, as a factory reset would."""

    rt.store.clear()
    rt.metrics.clear_local()
    return {"reset": True, "keys": rt.store.count()}
