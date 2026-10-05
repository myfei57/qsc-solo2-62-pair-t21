"""Plain text control report."""

from __future__ import annotations

from coldstore.ns import Stage, control_line

from .describe import collect as collect_describe
from .runtime import Runtime
from .telemetry import collect as collect_telemetry


def text_report(rt: Runtime) -> str:
    """Render the operator report that mirrors the JSON snapshot."""

    describe = collect_describe(rt)
    telemetry = collect_telemetry(rt)
    line = control_line()
    rows = [
        "coldstore control report",
        f"pipeline: {describe['pipeline']}",
        f"pipeline stages={line.count()} contains_ammonia={line.contains(Stage.AMMONIA)}",
        f"store: {describe['store']}",
        f"rooms: {describe['rooms']}",
        f"compressors: {describe['compressors']}",
        f"supply: {describe['supply']}",
        f"temp: {describe['temp']}",
        f"ammonia: {describe['ammonia']}",
        f"interlock: {describe['interlock']}",
        f"cold_fans: {describe['cold_fans']}",
        f"evap: {describe['evap']}",
        f"defrost: {describe['defrost']}",
        f"load: {describe['load']}",
        f"quota: {describe['quota']}",
        f"audit: {describe['audit']}",
        f"audit kinds={rt.auditor.kinds()}",
        (
            f"compressors running={telemetry.compressors_running} "
            f"stage={telemetry.total_stage}/{telemetry.max_stage} "
            f"ratio={telemetry.load_ratio:.4f}"
        ),
        f"compressor ids={rt.compressors.compressor_ids()} order={rt.compressors.order()}",
        (
            f"rooms defrosting={telemetry.defrosting} warmups={telemetry.defrost_warmups} "
            f"hottest={rt.rooms.hottest() or ''}"
        ),
        (
            f"temp value={telemetry.temp_value:.4f} rate={telemetry.temp_rate:.4f} "
            f"within={telemetry.temp_within}"
        ),
        (
            f"ammonia last={telemetry.ammonia_last:.4f} "
            f"latched={telemetry.ammonia_latched} trips={telemetry.interlock_trips}"
        ),
        (
            f"evap temperature={telemetry.evap_temperature:.4f} "
            f"above={telemetry.evap_above} duty={rt.evap.duty() or ''}"
        ),
        f"cooling load={telemetry.cooling_load:.4f} due={telemetry.schedule_due}",
        f"quota value={telemetry.quota_value:.4f} open valves={telemetry.supply_open}",
    ]
    return "\n".join(rows) + "\n"
