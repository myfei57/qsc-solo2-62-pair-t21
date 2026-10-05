"""Single source of truth for the console route table."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from .http import Router


@dataclass(frozen=True)
class Route:
    """One console endpoint and the handler attribute that serves it."""

    method: str
    path: str
    note: str
    handler: str

    def as_dict(self) -> dict[str, str]:
        return {"method": self.method, "path": self.path, "note": self.note}


def route_table() -> list[Route]:
    """Every route the console serves, in catalog order."""

    return [
        Route("GET", "/health", "service health and persisted keys", "health"),
        Route("GET", "/health/checks", "detailed component health checks", "health_checks"),
        Route("GET", "/snapshot", "full component snapshot", "snapshot"),
        Route("GET", "/describe", "human readable component summary", "describe"),
        Route("GET", "/report", "plain text control report", "report"),
        Route("GET", "/pipeline", "control pipeline stages", "pipeline"),
        Route("GET", "/catalog", "list all HTTP routes", "catalog"),
        Route("GET", "/ops", "operator counters", "ops_counters"),
        Route("POST", "/ops/reset-store", "factory reset persisted store", "ops_reset_store"),
        Route("GET", "/telemetry", "runtime telemetry counters", "telemetry"),
        Route("GET", "/version", "build version information", "version"),
        Route("GET", "/system", "runtime system information", "system"),
        Route("POST", "/history", "append a console event", "history_append"),
        Route("GET", "/history", "list console events", "history_list"),
        Route("POST", "/history/clear", "clear console events", "history_clear"),
        Route("GET", "/metrics", "console request counters", "metrics"),
        Route("POST", "/metrics/reset", "reset console request counters", "metrics_reset"),
        Route("POST", "/room/add", "add a cold room", "room_add"),
        Route("POST", "/room/remove", "remove a cold room", "room_remove"),
        Route("POST", "/room/assign", "assign a compressor to a room", "room_assign"),
        Route("POST", "/room/sensor", "assign an ammonia sensor to a room", "room_sensor"),
        Route("POST", "/room/renumber", "renumber a cold room zone", "room_renumber"),
        Route("POST", "/room/temp", "set the stored room temperature", "room_temp_set"),
        Route("GET", "/room/temp", "read the stored room temperature", "room_temp_get"),
        Route("POST", "/room/lookup", "read a room zone and assignment", "room_lookup"),
        Route("GET", "/room/compressor", "rooms served by a compressor", "room_compressor"),
        Route("POST", "/room/reset", "reset every defrosting flag", "room_reset"),
        Route("GET", "/rooms", "list every cold room", "rooms_list"),
        Route("GET", "/temp", "current temperature and rate state", "temp_state"),
        Route("POST", "/temp/read", "record a room temperature reading", "temp_read"),
        Route("GET", "/temp/verdict", "rate window verdict", "temp_verdict"),
        Route("POST", "/temp/window", "set the temperature rate window", "temp_window"),
        Route("GET", "/temp/readings", "list recorded temperature readings", "temp_readings"),
        Route("POST", "/temp/reset", "clear recorded temperature readings", "temp_reset"),
        Route("POST", "/comp/add", "add a compressor", "comp_add"),
        Route("POST", "/comp/remove", "remove a compressor", "comp_remove"),
        Route("GET", "/comp", "compressor bank state", "comp_state"),
        Route("POST", "/comp/lookup", "read a single compressor", "comp_lookup"),
        Route("POST", "/comp/stage", "set a compressor load stage", "comp_stage"),
        Route("POST", "/comp/start", "start a compressor", "comp_start"),
        Route("POST", "/comp/stop", "stop a compressor", "comp_stop"),
        Route("GET", "/comp/order", "loading order and headroom", "comp_order"),
        Route("POST", "/comp/reserve", "reserve a compressor for a room", "comp_reserve"),
        Route("POST", "/comp/release", "release a compressor reservation", "comp_release"),
        Route("GET", "/comp/reservations", "list compressor reservations", "comp_reservations"),
        Route("GET", "/valve", "supply valve state", "valve_state"),
        Route("POST", "/valve/open", "open a supply valve", "valve_open"),
        Route("POST", "/valve/close", "close a supply valve", "valve_close"),
        Route("POST", "/valve/position", "set a validated valve position", "valve_position"),
        Route("POST", "/valve/start", "open the valve then start the compressor", "valve_start"),
        Route("POST", "/valve/stop", "stop the compressor then close the valve", "valve_stop"),
        Route("POST", "/fan/add", "add a cold air fan", "fan_add"),
        Route("GET", "/fan", "cold air fan state", "fan_state"),
        Route("POST", "/fan/lookup", "read a single cold air fan", "fan_lookup"),
        Route("POST", "/fan/start", "start a cold air fan", "fan_start"),
        Route("POST", "/fan/stop", "stop a cold air fan", "fan_stop"),
        Route("POST", "/fan/switch", "switch primary fan duty", "fan_switch"),
        Route("POST", "/fan/fail", "mark a fan faulted", "fan_fail"),
        Route("POST", "/fan/repair", "clear a fan fault", "fan_repair"),
        Route("GET", "/fan/faults", "faulted and running fans", "fan_faults"),
        Route("GET", "/evap", "evaporative condenser state", "evap_state"),
        Route("POST", "/evap/baseline", "set the condenser temperature baseline", "evap_baseline"),
        Route("POST", "/evap/temp", "record the condenser temperature", "evap_temp"),
        Route("POST", "/evap/switch", "switch the evaporative duty fan", "evap_switch"),
        Route("GET", "/defrost", "defrost queue and warm up state", "defrost_state"),
        Route("POST", "/defrost/start", "start a defrost sequence", "defrost_start"),
        Route("POST", "/defrost/finish", "finish a defrost sequence", "defrost_finish"),
        Route("POST", "/defrost/enqueue", "enqueue a defrost command", "defrost_enqueue"),
        Route("POST", "/defrost/replay", "replay queued defrost commands", "defrost_replay"),
        Route("POST", "/defrost/recover", "recover and discard stale commands", "defrost_recover"),
        Route("POST", "/defrost/select", "select a room by zone", "defrost_select"),
        Route("GET", "/ammonia", "ammonia monitor state", "ammonia_state"),
        Route("POST", "/ammonia/read", "record an ammonia reading", "ammonia_read"),
        Route("GET", "/ammonia/verdict", "latest ammonia verdict", "ammonia_verdict"),
        Route("POST", "/ammonia/threshold", "set the calibrated trip threshold", "ammonia_threshold"),
        Route("POST", "/ammonia/calibrate", "set the ammonia calibration factor", "ammonia_calibrate"),
        Route("POST", "/ammonia/reset", "clear the ammonia latch", "ammonia_reset"),
        Route("GET", "/interlock", "safety interlock state", "interlock_state"),
        Route("POST", "/interlock/trip", "latch the interlock", "interlock_trip"),
        Route("POST", "/interlock/reset", "clear the interlock latch", "interlock_reset"),
        Route("GET", "/interlock/trips", "list recorded interlock trips", "interlock_trips"),
        Route("POST", "/interlock/clear", "clear the interlock trip log", "interlock_clear"),
        Route("GET", "/load", "cooling load state", "load_state"),
        Route("POST", "/load/baseline", "set the cooling load baseline", "load_baseline"),
        Route("POST", "/load/coefficient", "set the cooling load coefficient", "load_coefficient"),
        Route("POST", "/load/estimate", "estimate load for one temperature", "load_estimate"),
        Route("POST", "/quota/add", "accumulate runtime quota", "quota_add"),
        Route("GET", "/quota", "read the runtime accumulator", "quota_get"),
        Route("POST", "/quota/remaining", "remaining runtime allowance", "quota_remaining"),
        Route("POST", "/quota/check", "check a runtime quota", "quota_check"),
        Route("POST", "/quota/reset", "reset the runtime accumulator", "quota_reset"),
        Route("GET", "/audit", "list runtime audit entries", "audit_list"),
        Route("GET", "/audit/summary", "audit entry count by kind", "audit_summary"),
        Route("POST", "/audit/filter", "filter audit entries by kind", "audit_filter"),
        Route("GET", "/audit/totals", "summed amount per entry kind", "audit_totals"),
        Route("GET", "/schedule", "defrost schedule for the rooms", "schedule_state"),
        Route("POST", "/schedule/threshold", "set the defrost temperature threshold", "schedule_threshold"),
        Route("POST", "/schedule/plan", "plan defrost order by temperature", "schedule_plan"),
        Route("GET", "/export/audit", "runtime audit trail as CSV", "export_audit"),
        Route("GET", "/export/telemetry", "telemetry counters as CSV", "export_telemetry"),
        Route("POST", "/cycle", "run a full control cycle", "cycle"),
        Route("POST", "/simulate", "run deterministic simulation ticks", "simulate"),
    ]


def register_routes(router: Router, handlers: ModuleType) -> None:
    """Bind every catalogued route to its handler function."""

    for route in route_table():
        router.add(route.method, route.path, getattr(handlers, route.handler))
