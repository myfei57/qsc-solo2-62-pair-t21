"""One full refrigeration control cycle."""

from __future__ import annotations

from coldstore.ammonia import validate_ppm
from coldstore.quota import validate_amount
from coldstore.temp import validate_temp

from .http import Request, Response, json_response
from .runtime import Runtime


def run_cycle(rt: Runtime, request: Request) -> Response:
    """Walk the whole control line once, in production order."""

    room_id = request.str_field("room_id")
    comp_id = request.str_field("comp_id")
    temp = request.float_field("temp")
    ppm = request.float_field("ppm")
    amount = request.float_field("amount")
    defrost = request.int_field("defrost")

    validate_temp(temp)
    validate_ppm(ppm)
    validate_amount(amount)

    verdict = rt.temp.record(temp)
    ammonia = rt.ammonia.detect(ppm)
    tripped = False
    if ammonia.trip:
        rt.interlock.trip(f"ammonia {ammonia.calibrated:.2f} ppm")
        if comp_id:
            rt.supply.stop_with_supply(rt.compressors, comp_id)
        tripped = True
    else:
        if comp_id:
            if rt.load.is_high(temp):
                rt.compressors.stage_up(comp_id)
            else:
                rt.compressors.stage_down(comp_id)
            rt.supply.start_with_supply(rt.compressors, comp_id)
        if defrost and room_id:
            rt.defrost.start(room_id)
        elif room_id:
            rt.defrost.finish(room_id)

    quota_value = rt.accumulator.add(amount)
    rt.auditor.record("cycle", f"{temp:.4f}")

    return json_response(
        {
            "temp": verdict.value,
            "rate": verdict.rate,
            "within_window": verdict.within,
            "ammonia_level": ammonia.level,
            "tripped": tripped,
            "stage": rt.compressors.stage(comp_id)[0] if comp_id else 0,
            "supply_open": rt.supply.is_open(comp_id) if comp_id else False,
            "defrosting": rt.defrost.defrosting(),
            "quota": quota_value,
            "cooling_load": rt.load.load_for(temp),
            "audit_count": rt.auditor.count(),
        }
    )
