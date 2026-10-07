"""Tests for the unified, persistent, sampled request counters."""

from __future__ import annotations

import json
import tempfile
import unittest

from coldstore.audit import Auditor
from coldstore.console.metrics import METRICS_KEY, Metrics
from coldstore.console.seed import seed_defaults
from coldstore.console.server import Server
from coldstore.store import Store


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class MetricsUnitCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store.open(f"{self._tmp.name}/state.json")
        self.auditor = Auditor(self.store)
        self.clock = FakeClock()

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def make_metrics(self, **kwargs) -> Metrics:
        return Metrics(self.store, self.auditor, clock=self.clock, **kwargs)

    def test_flush_is_rate_limited(self) -> None:
        metrics = self.make_metrics(flush_interval=5.0, flush_every=1000)
        for _ in range(500):
            metrics.record("GET", "/health", 200)
        self.assertEqual(metrics.snapshot().flushes, 0)
        self.assertFalse(self.store.get(METRICS_KEY)[1])

        self.clock.advance(5.0)
        metrics.record("GET", "/health", 200)
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot.flushes, 1)
        raw, present = self.store.get(METRICS_KEY)
        self.assertTrue(present)
        self.assertEqual(json.loads(raw)["requests"], 501)

    def test_flush_every_caps_the_window(self) -> None:
        metrics = self.make_metrics(flush_interval=3600.0, flush_every=100)
        for _ in range(250):
            metrics.record("GET", "/health", 200)
        self.assertEqual(metrics.snapshot().flushes, 2)

    def test_sampler_drops_decades_under_load(self) -> None:
        metrics = self.make_metrics(sample_threshold=10.0)
        for _ in range(200):
            metrics.record("GET", "/health", 200)
        self.clock.advance(1.0)
        metrics.flush()
        self.assertEqual(metrics.snapshot().sample_rate, 0.01)

        for _ in range(1000):
            metrics.record("GET", "/busy", 200)
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot.requests, 1200)
        self.assertEqual(snapshot.by_route["GET /health"], 200)
        self.assertEqual(snapshot.by_route["GET /busy"], 1000)
        self.assertTrue(snapshot.as_dict()["estimated"])

    def test_totals_stay_exact_when_sampled(self) -> None:
        metrics = self.make_metrics(sample_threshold=1.0)
        self.clock.advance(1.0)
        for _ in range(100):
            metrics.record("GET", "/boom", 500)
        metrics.flush()
        self.assertLess(metrics.snapshot().sample_rate, 1.0)

        for _ in range(50):
            metrics.record("GET", "/boom", 500)
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot.requests, 150)
        self.assertEqual(snapshot.errors, 150)

    def test_restart_continues_persisted_totals(self) -> None:
        metrics = self.make_metrics()
        for _ in range(7):
            metrics.record("GET", "/health", 200)
        metrics.record("GET", "/missing", 404)
        metrics.close()

        reopened = Store.open(self.store.path)
        try:
            resumed = Metrics(reopened, Auditor(reopened), clock=self.clock)
            snapshot = resumed.snapshot()
            self.assertEqual(snapshot.requests, 8)
            self.assertEqual(snapshot.errors, 1)
            self.assertEqual(snapshot.by_route["GET /health"], 7)
            resumed.record("GET", "/health", 200)
            self.assertEqual(resumed.snapshot().requests, 9)
        finally:
            reopened.close()

    def test_reset_is_explicit_audited_and_persisted(self) -> None:
        metrics = self.make_metrics()
        metrics.record("GET", "/health", 200)
        metrics.reset()
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot.requests, 0)
        self.assertEqual(snapshot.resets, 1)
        kinds = [entry.kind for entry in self.auditor.entries()]
        self.assertIn("metrics.reset", kinds)
        raw, present = self.store.get(METRICS_KEY)
        self.assertTrue(present)
        self.assertEqual(json.loads(raw)["requests"], 0)

        resumed = Metrics(self.store, self.auditor, clock=self.clock)
        self.assertEqual(resumed.snapshot().resets, 1)

    def test_flush_writes_one_audit_entry_with_delta_and_total(self) -> None:
        metrics = self.make_metrics()
        for _ in range(3):
            metrics.record("GET", "/health", 200)
        metrics.flush()
        entries = [entry for entry in self.auditor.entries() if entry.kind == "metrics.flush"]
        self.assertEqual(len(entries), 1)
        detail = json.loads(entries[0].detail)
        self.assertEqual(detail["requests"], 3)
        self.assertEqual(detail["delta"], 3)
        self.assertEqual(detail["errors"], 0)
        self.assertEqual(detail["sample_rate"], 1.0)


class MetricsConsoleCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store.open(f"{self._tmp.name}/state.json")
        seed_defaults(self.store)
        self.server = Server(self.store)

    def tearDown(self) -> None:
        self.server.close()
        self.store.close()
        self._tmp.cleanup()

    def call(self, method: str, path: str, payload: dict | None = None):
        response = self.server.dispatch(method, path, payload)
        body = response.body.decode("utf-8")
        parsed = json.loads(body) if response.content_type.startswith("application/json") else body
        return response.status, parsed

    def test_panel_telemetry_and_export_read_one_source(self) -> None:
        self.call("GET", "/health")
        self.call("GET", "/missing")
        _, metrics = self.call("GET", "/metrics")
        _, telemetry = self.call("GET", "/telemetry")
        _, ops = self.call("GET", "/ops")
        _, export = self.call("GET", "/export/metrics")

        self.assertEqual(metrics["requests"], 2)
        self.assertEqual(metrics["errors"], 1)
        # Each read serves the same counter; the requesting call is counted
        # after its snapshot, so each later reader sees exactly one more.
        self.assertEqual(telemetry["requests"], metrics["requests"] + 1)
        self.assertEqual(ops["requests"], telemetry["requests"] + 1)
        self.assertEqual(telemetry["errors"], 1)
        self.assertEqual(ops["errors"], 1)
        self.assertEqual(telemetry["metrics_sample_rate"], 1.0)
        self.assertIn(f"requests,{ops['requests'] + 1}", export)
        self.assertIn("errors,1", export)

    def test_definitions_declare_the_caliber(self) -> None:
        status, body = self.call("GET", "/metrics/definitions")
        self.assertEqual(status, 200)
        self.assertEqual(body["sync"], "cumulative")
        self.assertEqual(body["restart"], "continue")
        names = {definition["name"] for definition in body["definitions"]}
        self.assertEqual(names, {"requests", "errors", "by_status", "by_route"})

    def test_restart_continues_counters_end_to_end(self) -> None:
        self.call("GET", "/health")
        self.call("GET", "/health")
        _, before = self.call("GET", "/metrics")
        self.assertEqual(before["requests"], 2)
        self.server.close()
        self.store.close()

        reopened = Store.open(self.store.path)
        try:
            seed_defaults(reopened)
            server2 = Server(reopened)
            response = server2.dispatch("GET", "/metrics")
            body = json.loads(response.body.decode("utf-8"))
            self.assertEqual(body["requests"], 3)
            self.assertTrue(body["persisted"])

            response = server2.dispatch("GET", "/history")
            events = json.loads(response.body.decode("utf-8"))["events"]
            self.assertTrue(
                any(
                    event["kind"] == "metrics" and "restored requests=3" in event["value"]
                    for event in events
                )
            )
            server2.close()
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
