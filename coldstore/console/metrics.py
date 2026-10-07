"""Request counters gathered by the console.

Counting rules (the single caliber every surface agrees on):

- every routed request counts once, including 4xx and 5xx responses;
- a response with status >= 400 also counts as an error;
- counters are cumulative: they survive restarts and are only zeroed by
  an explicit reset or by a factory reset of the store.

Sync rules: deltas accumulate in memory and the store only ever receives
a cumulative snapshot. Reloading a snapshot is idempotent, so a crash
loses at most the unflushed tail, which the flush policy bounds.

Flush policy (rate limited sampling): the snapshot is persisted at most
once per ``FLUSH_EVERY`` recorded requests and at most once per
``FLUSH_SECONDS`` while traffic keeps arriving, whichever comes first.
Resets and shutdown flush immediately because operator intent must be
durable. Flushes are not audited; restores and resets are.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

from coldstore.audit import Auditor
from coldstore.store import Store

METRICS_KEY = "console:metrics"
FLUSH_EVERY = 16
FLUSH_SECONDS = 5.0


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


@dataclass(frozen=True)
class MetricsSnapshot:
    """Cumulative counters plus the bookkeeping an operator audits."""

    requests: int
    errors: int
    by_status: dict[int, int]
    by_route: dict[str, int]
    resets: int
    since: str
    restored: int
    pending: int

    def as_dict(self) -> dict[str, object]:
        return {
            "requests": self.requests,
            "errors": self.errors,
            "by_status": {str(status): count for status, count in self.by_status.items()},
            "by_route": self.by_route,
            "resets": self.resets,
            "since": self.since,
            "restored": self.restored,
            "pending": self.pending,
        }


class Metrics:
    """Thread safe request counters persisted as cumulative snapshots."""

    def __init__(self, store: Store, auditor: Auditor | None = None) -> None:
        self._store = store
        self._auditor = auditor
        self._lock = threading.RLock()
        self._requests = 0
        self._errors = 0
        self._by_status: dict[int, int] = {}
        self._by_route: dict[str, int] = {}
        self._resets = 0
        self._since = _now_iso()
        self._restored = 0
        self._pending = 0
        self._last_flush = time.monotonic()
        self._restore()

    def _restore(self) -> None:
        """Adopt the persisted cumulative snapshot, if one exists."""

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
        raw_status = payload.get("by_status")
        if isinstance(raw_status, dict):
            for key, value in raw_status.items():
                count = _as_int(value)
                try:
                    status = int(key)
                except (TypeError, ValueError):
                    continue
                if count > 0:
                    self._by_status[status] = count
        raw_route = payload.get("by_route")
        if isinstance(raw_route, dict):
            self._by_route = {
                str(route): count
                for route, count in ((str(route), _as_int(count)) for route, count in raw_route.items())
                if count > 0
            }
        self._resets = _as_int(payload.get("resets"))
        since = payload.get("since")
        if isinstance(since, str) and since:
            self._since = since
        self._restored = self._requests
        if self._requests and self._auditor is not None:
            self._auditor.record(
                "metrics",
                f"restored requests={self._requests} errors={self._errors} resets={self._resets}",
            )

    def record(self, method: str, path: str, status: int) -> None:
        with self._lock:
            self._requests += 1
            self._by_status[status] = self._by_status.get(status, 0) + 1
            route = f"{method} {path}"
            self._by_route[route] = self._by_route.get(route, 0) + 1
            if status >= 400:
                self._errors += 1
            self._pending += 1
            now = time.monotonic()
            if self._pending >= FLUSH_EVERY or now - self._last_flush >= FLUSH_SECONDS:
                self._flush_locked()

    def _flush_locked(self) -> None:
        payload = {
            "requests": self._requests,
            "errors": self._errors,
            "by_status": {str(status): count for status, count in self._by_status.items()},
            "by_route": self._by_route,
            "resets": self._resets,
            "since": self._since,
        }
        self._store.put(METRICS_KEY, json.dumps(payload, ensure_ascii=False, sort_keys=True))
        self._pending = 0
        self._last_flush = time.monotonic()

    def flush(self) -> None:
        """Persist any unflushed tail, used on shutdown."""

        with self._lock:
            if self._pending:
                self._flush_locked()

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                requests=self._requests,
                errors=self._errors,
                by_status=dict(self._by_status),
                by_route=dict(self._by_route),
                resets=self._resets,
                since=self._since,
                restored=self._restored,
                pending=self._pending,
            )

    def reset(self) -> None:
        """Zero the counters, durably, and leave an audit trail."""

        with self._lock:
            before_requests = self._requests
            before_errors = self._errors
            self._requests = 0
            self._errors = 0
            self._by_status = {}
            self._by_route = {}
            self._resets += 1
            self._since = _now_iso()
            self._restored = 0
            self._flush_locked()
            if self._auditor is not None:
                self._auditor.record(
                    "metrics",
                    f"reset before requests={before_requests} errors={before_errors}",
                )

    def clear_local(self) -> None:
        """Zero the in-memory counters without persisting (factory reset)."""

        with self._lock:
            self._requests = 0
            self._errors = 0
            self._by_status = {}
            self._by_route = {}
            self._resets = 0
            self._since = _now_iso()
            self._restored = 0
            self._pending = 0
