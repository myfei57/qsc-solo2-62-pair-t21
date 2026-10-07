"""Operator counters and store reset."""

from __future__ import annotations

from dataclasses import dataclass

from .runtime import Runtime


@dataclass(frozen=True)
class OpsCounters:
    """Small set of counters shown on the operator page."""

    store_keys: int
    rooms: int
    compressors: int
    running: int
    supply_open: int
    audit_entries: int
    requests: int
    errors: int

    def as_dict(self) -> dict[str, object]:
        return {
            "store_keys": self.store_keys,
            "rooms": self.rooms,
            "compressors": self.compressors,
            "running": self.running,
            "supply_open": self.supply_open,
            "audit_entries": self.audit_entries,
            "requests": self.requests,
            "errors": self.errors,
        }


def collect(rt: Runtime) -> OpsCounters:
    metrics = rt.metrics.snapshot()
    return OpsCounters(
        store_keys=rt.store.count(),
        rooms=rt.rooms.count(),
        compressors=rt.compressors.count(),
        running=rt.compressors.running_count(),
        supply_open=len(rt.supply.opened_ids()),
        audit_entries=rt.auditor.count(),
        requests=metrics.requests,
        errors=metrics.errors,
    )


def reset_store(rt: Runtime) -> dict[str, object]:
    """Clear every persisted key, as a factory reset would."""

    rt.store.clear()
    rt.metrics.reset(persist=False)
    return {"reset": True, "keys": rt.store.count()}
