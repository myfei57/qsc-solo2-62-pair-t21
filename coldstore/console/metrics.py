"""Request counters with one persistent, sampled, audited pipeline.

The counting rules ("口径") are declared once here and apply to every reader
(/metrics, /telemetry, /ops, /export/metrics all serve the same snapshot):

* Counters are cumulative and monotonic. They are persisted and synced as
  cumulative totals; deltas are derived by readers, never stored as truth.
* A restart continues the persisted totals. Counters are never zeroed by a
  restart, only by an explicit reset, which is audited.
* Recording is O(1) in memory. Persistence is rate limited: at most one
  flush per ``flush_interval`` seconds or per ``flush_every`` requests.
* Totals (requests, errors) are always exact. Detailed dimensions
  (by_status, by_route) are sampled down in decades when the request rate
  exceeds ``sample_threshold`` requests per second; kept entries are
  weighted so the detailed sums still estimate the exact totals.
* Every flush and every reset appends one audit entry, so the persisted
  counters can be reconciled against the audit trail.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from coldstore.store import Store, append_event

from .history import EVENT_KEY

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from coldstore.audit import Auditor

METRICS_KEY = "metrics:counters"
FLUSH_AUDIT_KIND = "metrics.flush"
RESET_AUDIT_KIND = "metrics.reset"

DEFAULT_FLUSH_INTERVAL = 5.0
DEFAULT_FLUSH_EVERY = 1000
DEFAULT_SAMPLE_THRESHOLD = 100.0
MAX_SAMPLE_DECADE = 3


@dataclass(frozen=True)
class MetricDefinition:
    """The declared caliber of one metric: what it counts and how."""

    name: str
    kind: str
    unit: str
    note: str
    sampled: bool
    persisted: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "unit": self.unit,
            "note": self.note,
            "sampled": self.sampled,
            "persisted": self.persisted,
        }


DEFINITIONS = (
    MetricDefinition(
        "requests", "counter", "requests", "every console request, exact and monotonic", False, True
    ),
    MetricDefinition(
        "errors", "counter", "requests", "responses with status >= 400, exact", False, True
    ),
    MetricDefinition(
        "by_status", "counter", "requests", "requests per status, sampled under load", True, True
    ),
    MetricDefinition(
        "by_route", "counter", "requests", "requests per route, sampled under load", True, True
    ),
)


def definitions(
    flush_interval: float = DEFAULT_FLUSH_INTERVAL,
    flush_every: int = DEFAULT_FLUSH_EVERY,
    sample_threshold: float = DEFAULT_SAMPLE_THRESHOLD,
) -> dict[str, object]:
    """The declared counting rules, served to operators and auditors."""

    return {
        "sync": "cumulative",
        "restart": "continue",
        "reset": "explicit only, audited",
        "flush_interval": flush_interval,
        "flush_every": flush_every,
        "sample_threshold": sample_threshold,
        "definitions": [definition.as_dict() for definition in DEFINITIONS],
    }


@dataclass(frozen=True)
class MetricsSnapshot:
    """Counters accumulated since the last explicit reset."""

    requests: int
    errors: int
    by_status: dict[int, int]
    by_route: dict[str, int]
    sample_rate: float
    flushes: int
    resets: int
    persisted: bool
    started_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "requests": self.requests,
            "errors": self.errors,
            "by_status": {str(status): count for status, count in self.by_status.items()},
            "by_route": self.by_route,
            "sample_rate": self.sample_rate,
            "estimated": self.sample_rate < 1.0,
            "flushes": self.flushes,
            "resets": self.resets,
            "persisted": self.persisted,
            "started_at": self.started_at,
        }


class Sampler:
    """Adaptive systematic sampler for the detailed dimensions.

    Keeps exactly one in every ``weight`` records, where the weight is a
    power of ten derived from the request rate of the last flush window.
    """

    def __init__(self, threshold: float) -> None:
        self._threshold = threshold
        self.rate = 1.0
        self._tick = 0

    @property
    def weight(self) -> int:
        return max(1, round(1.0 / self.rate))

    def update(self, window_requests: int, window_seconds: float) -> None:
        """Recompute the sample rate from the finished flush window."""

        if window_seconds <= 0 or window_requests <= 0:
            return
        rps = window_requests / window_seconds
        if rps <= self._threshold:
            self.rate = 1.0
            return
        excess = rps / self._threshold
        decade = min(MAX_SAMPLE_DECADE, max(1, math.ceil(math.log10(excess))))
        self.rate = 1.0 / (10**decade)

    def keep(self) -> bool:
        """Systematic keep: exactly one in every ``weight`` calls."""

        self._tick += 1
        if self._tick >= self.weight:
            self._tick = 0
            return True
        return False


class Metrics:
    """Thread safe request counters, persisted and audited via the store."""

    def __init__(
        self,
        store: Store | None = None,
        auditor: "Auditor | None" = None,
        *,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
        flush_every: int = DEFAULT_FLUSH_EVERY,
        sample_threshold: float = DEFAULT_SAMPLE_THRESHOLD,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.RLock()
        self._store = store
        self._auditor = auditor
        self._flush_interval = flush_interval
        self._flush_every = flush_every
        self._clock = clock
        self._sampler = Sampler(sample_threshold)
        self._requests = 0
        self._errors = 0
        self._by_status: dict[int, int] = {}
        self._by_route: dict[str, int] = {}
        self._window_requests = 0
        self._window_started = clock()
        self._last_flush = self._window_started
        self._since_flush = 0
        self._flushes = 0
        self._resets = 0
        self._started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if store is not None:
            self._load()

    def record(self, method: str, path: str, status: int) -> None:
        with self._lock:
            self._requests += 1
            self._window_requests += 1
            self._since_flush += 1
            if status >= 400:
                self._errors += 1
            if self._sampler.keep():
                weight = self._sampler.weight
                self._by_status[status] = self._by_status.get(status, 0) + weight
                route = f"{method} {path}"
                self._by_route[route] = self._by_route.get(route, 0) + weight
            self._maybe_flush_locked()

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                requests=self._requests,
                errors=self._errors,
                by_status=dict(self._by_status),
                by_route=dict(self._by_route),
                sample_rate=self._sampler.rate,
                flushes=self._flushes,
                resets=self._resets,
                persisted=self._store is not None,
                started_at=self._started_at,
            )

    def reset(self, persist: bool = True) -> None:
        """Zero every counter. Explicit and audited; never done on restart.

        With ``persist=False`` only the in-memory counters are zeroed; the
        caller has just cleared the store itself (factory reset) and the
        next rate limited flush writes the fresh totals.
        """

        with self._lock:
            self._requests = 0
            self._errors = 0
            self._by_status = {}
            self._by_route = {}
            self._resets += 1
            self._sampler.rate = 1.0
            self._window_requests = 0
            self._window_started = self._clock()
            self._last_flush = self._window_started
            self._since_flush = 0
            if not persist:
                return
            self._persist_locked()
            if self._auditor is not None:
                self._auditor.record(RESET_AUDIT_KIND, json.dumps({"resets": self._resets}))

    def flush(self) -> None:
        """Persist the cumulative counters now, outside the rate limit."""

        with self._lock:
            self._flush_locked()

    def close(self) -> None:
        """Final flush before shutdown so no counted request is lost."""

        self.flush()

    def _load(self) -> None:
        if self._store is None:
            return
        raw, present = self._store.get(METRICS_KEY)
        if not present:
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            return
        if not isinstance(payload, dict):
            return
        self._requests = _as_int(payload.get("requests"))
        self._errors = _as_int(payload.get("errors"))
        self._resets = _as_int(payload.get("resets"))
        by_status = payload.get("by_status")
        if isinstance(by_status, dict):
            for status, count in by_status.items():
                if str(status).isdigit():
                    self._by_status[int(status)] = _as_int(count)
        by_route = payload.get("by_route")
        if isinstance(by_route, dict):
            self._by_route = {str(route): _as_int(count) for route, count in by_route.items()}
        if self._requests > 0:
            append_event(
                self._store,
                EVENT_KEY,
                "metrics",
                f"restored requests={self._requests} errors={self._errors}",
            )

    def _maybe_flush_locked(self) -> None:
        if self._store is None:
            return
        now = self._clock()
        if self._since_flush >= self._flush_every or now - self._last_flush >= self._flush_interval:
            self._flush_locked(now)

    def _flush_locked(self, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        window_seconds = max(0.0, now - self._window_started)
        self._sampler.update(self._window_requests, window_seconds)
        self._persist_locked()
        self._flushes += 1
        if self._auditor is not None:
            detail = {
                "requests": self._requests,
                "delta": self._window_requests,
                "errors": self._errors,
                "sample_rate": self._sampler.rate,
            }
            self._auditor.record(
                FLUSH_AUDIT_KIND, json.dumps(detail, ensure_ascii=False, sort_keys=True)
            )
        self._window_requests = 0
        self._window_started = now
        self._last_flush = now
        self._since_flush = 0

    def _persist_locked(self) -> None:
        if self._store is None:
            return
        payload = {
            "requests": self._requests,
            "errors": self._errors,
            "by_status": {str(status): count for status, count in sorted(self._by_status.items())},
            "by_route": dict(sorted(self._by_route.items())),
            "resets": self._resets,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._store.put(METRICS_KEY, json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0
