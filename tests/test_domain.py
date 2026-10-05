"""Behavioural tests for the control components."""

from __future__ import annotations

import tempfile
import unittest

from coldstore.ammonia import Monitor, level_for, validate_ppm
from coldstore.ammonia import validate_threshold as validate_ammonia_threshold
from coldstore.audit import Auditor
from coldstore.comp import Bank as CompressorBank
from coldstore.comp import validate_stage
from coldstore.defrost import Controller as DefrostController
from coldstore.evap import Condenser, validate_baseline as validate_evap_baseline
from coldstore.fan import PRIMARY, STANDBY, FanSet
from coldstore.interlock import Interlock
from coldstore.load import LoadCalculator, compute_load, validate_baseline
from coldstore.ns import Stage, control_line
from coldstore.quota import Accumulator, Quota, check_quota, validate_amount
from coldstore.reporting import audit_export, to_csv
from coldstore.room import RoomRegistry, validate_zone
from coldstore.scheduler import Scheduler, validate_threshold
from coldstore.store import (
    Store,
    advance_epoch,
    append_command,
    append_event,
    clear_commands,
    event_count,
    list_events,
    load_commands,
)
from coldstore.temp import Collector, validate_temp
from coldstore.valve import OPEN, SupplyValve, validate_valve


class StoreCase(unittest.TestCase):
    def test_round_trip_persists_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            store.put("alpha", "1")
            store.put("beta", "2")
            self.assertEqual(store.keys(), ["alpha", "beta"])
            self.assertEqual(store.count(), 2)
            self.assertEqual(store.get("alpha"), ("1", True))
            self.assertEqual(store.get("missing"), ("", False))
            store.delete("alpha")
            self.assertEqual(store.keys(), ["beta"])
            reopened = Store.open(f"{tmp}/state.json")
            self.assertEqual(reopened.get("beta"), ("2", True))
            store.clear()
            self.assertEqual(store.count(), 0)

    def test_command_lists_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            self.assertEqual(load_commands(store, "list"), [])
            append_command(store, "list", "one")
            append_command(store, "list", "two")
            self.assertEqual(load_commands(store, "list"), ["one", "two"])
            clear_commands(store, "list")
            self.assertEqual(load_commands(store, "list"), [])

    def test_epoch_wraps_and_stays_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            self.assertEqual(advance_epoch(store, "counter", 40.0, 100.0), 40.0)
            self.assertEqual(advance_epoch(store, "counter", 90.0, 100.0), 30.0)
            self.assertGreaterEqual(advance_epoch(store, "counter", 95.0, 100.0), 0.0)

    def test_history_records_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            append_event(store, "events", "seed", "defaults")
            append_event(store, "events", "manual", "operator")
            events = list_events(store, "events")
            self.assertEqual([event.kind for event in events], ["seed", "manual"])
            self.assertEqual(event_count(store, "events"), 2)
            self.assertGreater(events[0].at, 0)


class PipelineCase(unittest.TestCase):
    def test_control_line_is_ordered(self) -> None:
        line = control_line()
        self.assertEqual(line.count(), 9)
        self.assertTrue(line.contains(Stage.AMMONIA))
        self.assertTrue(line.before(Stage.TEMP, Stage.COMP))
        self.assertTrue(line.before(Stage.COMP, Stage.VALVE))
        self.assertFalse(line.before(Stage.AUDIT, Stage.COMP))
        self.assertEqual(line.last(), Stage.AUDIT)
        self.assertEqual(len(line.steps()), 9)
        self.assertEqual(line.steps()[0].action, "sample room temperature")
        self.assertIn("control", line.describe())


class RoomCase(unittest.TestCase):
    def test_registry_lifecycle_and_assignments(self) -> None:
        rooms = RoomRegistry()
        rooms.add_room("r1", 1, -20.0)
        rooms.add_room("r2", 2, -5.0)
        self.assertEqual(rooms.count(), 2)
        self.assertEqual(rooms.room_ids(), ["r1", "r2"])
        self.assertEqual(rooms.hottest(), "r2")
        self.assertEqual(rooms.coldest(), "r1")
        self.assertEqual(rooms.average_temp(), -12.5)
        self.assertEqual(rooms.unassigned(), ["r1", "r2"])

        rooms.assign_compressor("r1", "c1")
        rooms.assign_sensor("r1", "a1")
        self.assertEqual(rooms.rooms_for_compressor("c1"), ["r1"])
        self.assertEqual(rooms.unassigned(), ["r2"])
        self.assertEqual(rooms.assignment("r1"), ("c1", "a1", True))
        self.assertEqual(rooms.temp("r1"), (-20.0, True))
        self.assertEqual(rooms.mapping(), {1: "r1", 2: "r2"})

        rooms.renumber("r2", 9)
        self.assertEqual(rooms.room_zone("r2"), (9, True))
        self.assertEqual(rooms.mapping()[9], "r2")

        rooms.set_defrosting("r1", True)
        self.assertEqual(rooms.defrosting_ids(), ["r1"])
        rooms.reset_defrosting()
        self.assertEqual(rooms.defrosting_ids(), [])

        self.assertIn("cold rooms=2", rooms.describe())
        rooms.set_temp("r1", -30.0)
        self.assertEqual(rooms.coldest(), "r1")
        state = rooms.state()
        self.assertEqual(state.count, 2)
        self.assertEqual(state.average_temp, -17.5)

        rooms.remove_room("r1")
        self.assertEqual(rooms.count(), 1)
        self.assertEqual(rooms.room("r1"), None)

    def test_unknown_room_raises(self) -> None:
        rooms = RoomRegistry()
        with self.assertRaises(ValueError):
            rooms.remove_room("missing")
        with self.assertRaises(ValueError):
            rooms.set_temp("missing", 0.0)
        with self.assertRaises(ValueError):
            rooms.assign_compressor("missing", "c1")
        self.assertEqual(rooms.temp("missing"), (0.0, False))
        self.assertEqual(rooms.room_zone("missing"), (0, False))
        self.assertEqual(rooms.assignment("missing"), ("", "", False))
        self.assertEqual(rooms.hottest(), "")
        self.assertEqual(rooms.average_temp(), 0.0)

    def test_zone_validation(self) -> None:
        validate_zone(1)
        with self.assertRaises(ValueError):
            validate_zone(-1)
        with self.assertRaises(ValueError):
            validate_zone(200_000)


class TempCase(unittest.TestCase):
    def test_rate_window_and_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            collector = Collector(Store.open(f"{tmp}/state.json"))
            self.assertEqual(collector.window(), 0.5)
            self.assertEqual(collector.readings(), [])
            collector.record(0.0, at=0)
            verdict = collector.record(4.0, at=1)
            self.assertFalse(verdict.within)
            self.assertEqual(verdict.direction, "rising")
            self.assertEqual(collector.current(), 4.0)
            self.assertEqual(collector.rate(), 4.0)
            self.assertFalse(collector.within_window())
            self.assertEqual(collector.state().samples, 2)
            self.assertIn("temp value=4.0000", collector.describe())
            collector.reset()
            self.assertEqual(collector.readings(), [])

    def test_window_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            collector = Collector(Store.open(f"{tmp}/state.json"))
            self.assertEqual(collector.set_window(2.0), 2.0)
            with self.assertRaises(ValueError):
                collector.set_window(0)
            with self.assertRaises(ValueError):
                collector.set_window(5000)

    def test_temp_validation(self) -> None:
        validate_temp(-18.0)
        with self.assertRaises(ValueError):
            validate_temp(-200.0)
        with self.assertRaises(ValueError):
            validate_temp(200.0)


class FanCase(unittest.TestCase):
    def test_duty_and_faults(self) -> None:
        fans = FanSet()
        fans.add_fan("f1", PRIMARY)
        fans.add_fan("f2", STANDBY)
        self.assertEqual(fans.count(), 2)
        self.assertEqual(fans.fan_ids(), ["f1", "f2"])
        self.assertEqual(fans.primary(), "f1")
        self.assertEqual(fans.active(), "")
        fans.start("f1")
        self.assertEqual(fans.active(), "f1")
        self.assertEqual(fans.running_ids(), ["f1"])
        self.assertEqual(fans.healthy_standby(), "f2")

        self.assertEqual(fans.switch_over("f2"), "f2")
        self.assertEqual(fans.primary(), "f2")
        self.assertEqual(fans.active(), "")
        fans.start("f2")
        self.assertEqual(fans.active(), "f2")

        fans.fail("f2")
        self.assertEqual(fans.faulted_ids(), ["f2"])
        self.assertEqual(fans.active(), "")
        self.assertEqual(fans.healthy_standby(), "f1")
        with self.assertRaises(ValueError):
            fans.start("f2")
        with self.assertRaises(ValueError):
            fans.switch_over("f2")

        fans.repair("f2")
        self.assertEqual(fans.faulted_ids(), [])
        self.assertEqual(fans.fan("f2").role, STANDBY)
        fans.stop_all()
        self.assertEqual(fans.running_ids(), [])
        self.assertIn("fans=2", fans.describe())
        self.assertEqual(fans.state().count, 2)

    def test_unknown_fan_raises(self) -> None:
        fans = FanSet()
        with self.assertRaises(ValueError):
            fans.start("missing")
        with self.assertRaises(ValueError):
            fans.fail("missing")
        self.assertEqual(fans.fan("missing"), None)
        self.assertEqual(fans.primary(), "")


class CondenserCase(unittest.TestCase):
    def test_baseline_and_changeover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            fans = FanSet()
            fans.add_fan("e1", PRIMARY)
            fans.add_fan("e2", STANDBY)
            condenser = Condenser(store, fans)
            self.assertEqual(condenser.baseline(), 32.0)
            self.assertEqual(condenser.temperature(), 0.0)
            self.assertFalse(condenser.above_baseline())
            condenser.set_baseline(30.0)
            condenser.set_temperature(35.0)
            self.assertTrue(condenser.above_baseline())
            self.assertEqual(condenser.switch_to_standby("e2"), "e2")
            self.assertEqual(condenser.duty(), "e2")
            self.assertIn("evap temperature", condenser.describe())
            self.assertEqual(condenser.state().duty, "e2")

    def test_baseline_validation(self) -> None:
        validate_evap_baseline(20.0)
        with self.assertRaises(ValueError):
            validate_evap_baseline(-200.0)
        with self.assertRaises(ValueError):
            validate_evap_baseline(200.0)


class DefrostCase(unittest.TestCase):
    def test_start_stops_fan_before_warmup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            fans = FanSet()
            fans.add_fan("f1", PRIMARY)
            fans.start("f1")
            rooms = RoomRegistry()
            rooms.add_room("r1", 1)
            controller = DefrostController(fans, rooms, store)
            controller.start("r1")
            self.assertEqual(fans.running_ids(), [])
            self.assertFalse(controller.spilled())
            self.assertEqual(controller.warmups(), ["r1"])
            self.assertEqual(controller.last_warmup(), "r1")
            self.assertEqual(controller.defrosting(), ["r1"])
            controller.finish("r1")
            self.assertEqual(fans.running_ids(), ["f1"])
            self.assertEqual(controller.defrosting(), [])
            self.assertIn("defrost commands=0", controller.describe())

    def test_queue_replay_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            fans = FanSet()
            fans.add_fan("f1", PRIMARY)
            rooms = RoomRegistry()
            rooms.add_room("r1", 1)
            rooms.add_room("r2", 2)
            controller = DefrostController(fans, rooms, store)
            controller.enqueue("r1")
            controller.enqueue("r2")
            self.assertEqual(controller.pending_count(), 2)
            self.assertEqual(controller.replay(), ["r1", "r2"])
            self.assertEqual(controller.warmup_count(), 2)
            self.assertEqual(controller.select(2), "r2")
            with self.assertRaises(ValueError):
                controller.select(7)
            controller.recover()
            self.assertEqual(controller.command_list(), [])
            self.assertEqual(controller.state().commands, [])


class AmmoniaCase(unittest.TestCase):
    def test_thresholds_and_latch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitor = Monitor(Store.open(f"{tmp}/state.json"))
            self.assertEqual(monitor.threshold(), 25.0)
            self.assertEqual(monitor.calibration(), 1.0)
            verdict = monitor.detect(10.0)
            self.assertEqual(verdict.level, "ok")
            self.assertFalse(verdict.trip)
            self.assertFalse(monitor.latched())
            self.assertEqual(monitor.last(), 10.0)

            monitor.calibrate(2.0)
            warn = monitor.detect(10.0)
            self.assertEqual(warn.level, "warn")
            trip = monitor.detect(15.0)
            self.assertEqual(trip.level, "trip")
            self.assertTrue(trip.trip)
            self.assertTrue(monitor.latched())
            self.assertIn("ammonia last", monitor.describe())

            monitor.reset()
            self.assertFalse(monitor.latched())
            self.assertEqual(monitor.state().calibration, 2.0)

    def test_levels_and_validation(self) -> None:
        self.assertEqual(level_for(0.0, 25.0), "ok")
        self.assertEqual(level_for(20.0, 25.0), "warn")
        self.assertEqual(level_for(30.0, 25.0), "trip")
        self.assertEqual(level_for(5.0, 0.0), "trip")
        validate_ppm(0.0)
        with self.assertRaises(ValueError):
            validate_ppm(-1.0)
        with self.assertRaises(ValueError):
            validate_ppm(2_000_000.0)
        validate_ammonia_threshold(1.0)
        with self.assertRaises(ValueError):
            validate_ammonia_threshold(0.0)
        with tempfile.TemporaryDirectory() as tmp:
            monitor = Monitor(Store.open(f"{tmp}/state.json"))
            with self.assertRaises(ValueError):
                monitor.calibrate(0.0)


class InterlockCase(unittest.TestCase):
    def test_trip_latch_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            interlock = Interlock(Store.open(f"{tmp}/state.json"))
            self.assertFalse(interlock.is_tripped())
            self.assertEqual(interlock.reason(), "")
            entry = interlock.trip("ammonia high")
            self.assertTrue(interlock.is_tripped())
            self.assertEqual(interlock.reason(), "ammonia high")
            self.assertEqual(interlock.count(), 1)
            self.assertEqual(interlock.last_trip().reason, "ammonia high")
            self.assertEqual(entry.reason, "ammonia high")
            self.assertIn("interlock tripped=True", interlock.describe())

            interlock.reset()
            self.assertFalse(interlock.is_tripped())
            self.assertEqual(interlock.reason(), "")
            self.assertEqual(len(interlock.trips()), 1)
            interlock.clear_log()
            self.assertEqual(interlock.count(), 0)
            self.assertEqual(interlock.state().count, 0)


class CompressorCase(unittest.TestCase):
    def test_staged_loading_and_arbitration(self) -> None:
        bank = CompressorBank()
        bank.add_compressor("c1", 4)
        self.assertEqual(bank.count(), 1)
        self.assertEqual(bank.compressor_ids(), ["c1"])
        self.assertEqual(bank.stage_up("c1"), 1)
        self.assertTrue(bank.compressor("c1").running)
        self.assertEqual(bank.stage_up("c1"), 2)
        self.assertEqual(bank.set_stage("c1", 4), 4)
        self.assertEqual(bank.total_stage(), 4)
        self.assertEqual(bank.max_stage(), 4)
        self.assertEqual(bank.load_ratio(), 1.0)
        self.assertEqual(bank.order(), ["c1"])
        self.assertEqual(bank.running_ids(), ["c1"])
        self.assertEqual(bank.running_count(), 1)
        self.assertEqual(bank.stage("c1"), (4, True))

        bank.reserve("c1", "r1")
        self.assertEqual(bank.reserved_by("c1"), "r1")
        self.assertEqual(bank.reservations(), {"c1": "r1"})
        with self.assertRaises(ValueError):
            bank.reserve("c1", "r2")
        with self.assertRaises(ValueError):
            bank.release("c1", "r2")
        bank.release("c1", "r1")
        self.assertEqual(bank.reserved_by("c1"), "")

        bank.stage_down("c1")
        self.assertEqual(bank.stage("c1")[0], 3)
        bank.stop("c1")
        self.assertEqual(bank.stage("c1")[0], 0)
        bank.start("c1")
        self.assertEqual(bank.stage("c1")[0], 1)
        self.assertIn("comp compressors=1", bank.describe())
        self.assertEqual(bank.state().running, 1)

        bank.remove("c1")
        self.assertEqual(bank.count(), 0)

    def test_unknown_and_validation(self) -> None:
        bank = CompressorBank()
        with self.assertRaises(ValueError):
            bank.stage_up("missing")
        with self.assertRaises(ValueError):
            bank.remove("missing")
        bank.add_compressor("c1", 2)
        with self.assertRaises(ValueError):
            bank.set_stage("c1", 5)
        self.assertEqual(bank.stage("missing"), (0, False))
        validate_stage(1)
        with self.assertRaises(ValueError):
            validate_stage(-1)
        with self.assertRaises(ValueError):
            validate_stage(20)


class SupplyValveCase(unittest.TestCase):
    def test_open_before_start_and_stop_before_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            bank = CompressorBank()
            bank.add_compressor("c1", 3)
            supply = SupplyValve(store)
            self.assertEqual(supply.position("c1"), "closed")
            self.assertFalse(supply.is_open("c1"))

            supply.start_with_supply(bank, "c1")
            self.assertTrue(supply.is_open("c1"))
            self.assertTrue(bank.compressor("c1").running)
            self.assertEqual(supply.opened_ids(), ["c1"])

            supply.stop_with_supply(bank, "c1")
            self.assertFalse(bank.compressor("c1").running)
            self.assertEqual(supply.position("c1"), "closed")
            self.assertEqual(supply.opened_ids(), [])
            self.assertIn("supply valves_open=0", supply.describe())
            self.assertEqual(supply.state().opened, [])

    def test_position_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            supply = SupplyValve(Store.open(f"{tmp}/state.json"))
            self.assertEqual(supply.open_valve("c9"), OPEN)
            self.assertTrue(supply.is_open("c9"))
            self.assertEqual(supply.close_valve("c9"), "closed")
            validate_valve(OPEN)
            validate_valve("closed")
            with self.assertRaises(ValueError):
                validate_valve("half")


class LoadCase(unittest.TestCase):
    def test_load_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            calculator = LoadCalculator(store)
            self.assertEqual(calculator.baseline(), -18.0)
            self.assertEqual(calculator.coefficient(), 1.5)
            self.assertEqual(calculator.load_for(-10.0), 12.0)
            self.assertTrue(calculator.is_high(-10.0))
            self.assertEqual(calculator.load_for(-30.0), 0.0)
            self.assertFalse(calculator.is_high(-30.0))
            self.assertEqual(compute_load(-10.0, -18.0, 1.5), 12.0)

            rooms = RoomRegistry()
            rooms.add_room("r1", 1, -10.0)
            rooms.add_room("r2", 2, -30.0)
            self.assertEqual(calculator.total(rooms), 12.0)
            state = calculator.state(rooms)
            self.assertEqual(state.total, 12.0)
            self.assertEqual(len(state.entries), 2)
            self.assertTrue(state.entries[0].high)
            self.assertIn("load baseline", calculator.describe(rooms))

            calculator.set_baseline(-20.0)
            self.assertEqual(calculator.baseline(), -20.0)
            calculator.set_coefficient(2.0)
            self.assertEqual(calculator.coefficient(), 2.0)
            with self.assertRaises(ValueError):
                calculator.set_coefficient(0.0)
            self.assertEqual(calculator.estimate(-10.0).load, 20.0)

    def test_baseline_validation(self) -> None:
        validate_baseline(-18.0)
        with self.assertRaises(ValueError):
            validate_baseline(-200.0)
        with self.assertRaises(ValueError):
            validate_baseline(200.0)


class QuotaCase(unittest.TestCase):
    def test_accumulator_and_remaining(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            accumulator = Accumulator(Store.open(f"{tmp}/state.json"))
            self.assertEqual(accumulator.add(10.0), 10.0)
            self.assertEqual(accumulator.value(), 10.0)
            self.assertEqual(accumulator.remaining(30.0), 20.0)
            self.assertEqual(accumulator.remaining(5.0), 0.0)
            accumulator.reset()
            self.assertEqual(accumulator.value(), 0.0)
            self.assertIn("quota accumulator", accumulator.describe())
            self.assertEqual(accumulator.state().value, 0.0)

    def test_check_quota_and_validation(self) -> None:
        quota = Quota(resource="runtime", limit=100.0)
        self.assertEqual(check_quota(quota.resource, 40.0, quota.limit), (60.0, True))
        self.assertEqual(check_quota(quota.resource, 120.0, quota.limit), (-20.0, False))
        self.assertEqual(check_quota(quota.resource, 5.0, 0.0), (5.0, True))
        validate_amount(1.0)
        with self.assertRaises(ValueError):
            validate_amount(-1.0)


class AuditCase(unittest.TestCase):
    def test_entries_and_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auditor = Auditor(Store.open(f"{tmp}/state.json"))
            self.assertEqual(auditor.count(), 0)
            self.assertEqual(auditor.last(), None)
            auditor.record("comp", "1.0000")
            auditor.record("ammonia", "0.5000")
            auditor.record("comp", "2.0000")
            self.assertEqual(auditor.count(), 3)
            self.assertEqual(auditor.count_by_kind(), {"comp": 2, "ammonia": 1})
            self.assertEqual(len(auditor.filter("comp")), 2)
            self.assertEqual(auditor.kinds(), ["comp", "ammonia"])
            self.assertEqual(auditor.last().kind, "comp")
            self.assertEqual(auditor.state().count, 3)
            self.assertEqual(auditor.totals(), {"comp": 3.0, "ammonia": 0.5})
            self.assertIn("audit entries=3", auditor.describe())


class SchedulerCase(unittest.TestCase):
    def test_plan_and_due_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/state.json")
            rooms = RoomRegistry()
            rooms.add_room("r1", 1, -20.0)
            rooms.add_room("r2", 2, -8.0)
            rooms.add_room("r3", 3, -10.0)
            scheduler = Scheduler(store)
            self.assertEqual(scheduler.threshold(), -12.0)
            self.assertEqual(scheduler.due(rooms), ["r2", "r3"])
            plan = scheduler.plan(rooms)
            self.assertEqual([entry.room_id for entry in plan], ["r2", "r3", "r1"])
            self.assertEqual([entry.priority for entry in plan], [1, 2, 3])
            self.assertEqual(plan[0].defrost_seconds, 280)
            scheduler.set_threshold(-15.0)
            self.assertEqual(scheduler.due(rooms), ["r2", "r3"])
            self.assertEqual(scheduler.state(rooms).threshold, -15.0)
            self.assertIn("schedule threshold", scheduler.describe(rooms))

    def test_threshold_validation(self) -> None:
        validate_threshold(-12.0)
        with self.assertRaises(ValueError):
            validate_threshold(-200.0)
        with self.assertRaises(ValueError):
            validate_threshold(200.0)


class ReportingCase(unittest.TestCase):
    def test_csv_rendering_escapes_fields(self) -> None:
        text = to_csv(["a", "b"], [[1, "plain"], [2, "has,comma"], [3, 'has"quote']])
        self.assertTrue(text.startswith("a,b\n"))
        self.assertIn('2,"has,comma"', text)
        self.assertIn('3,"has""quote"', text)

    def test_audit_export_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auditor = Auditor(Store.open(f"{tmp}/state.json"))
            auditor.record("comp", "2.0000")
            columns, rows = audit_export(auditor)
            self.assertEqual(columns, ["time", "kind", "detail", "id"])
            self.assertEqual(rows[0][1], "comp")
            self.assertEqual(rows[0][2], "2.0000")


if __name__ == "__main__":
    unittest.main()
