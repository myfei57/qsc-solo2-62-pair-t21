"""Wiring of every control component behind the console."""

from __future__ import annotations

from coldstore.ammonia import Monitor
from coldstore.audit import Auditor
from coldstore.comp import Bank
from coldstore.defrost import Controller
from coldstore.evap import Condenser
from coldstore.fan import FanSet
from coldstore.interlock import Interlock
from coldstore.load import LoadCalculator
from coldstore.quota import Accumulator
from coldstore.room import RoomRegistry
from coldstore.scheduler import Scheduler
from coldstore.store import Store
from coldstore.temp import Collector
from coldstore.valve import SupplyValve


class Runtime:
    """Owns one instance of each control component for a single store."""

    def __init__(self, store: Store) -> None:
        rooms = RoomRegistry()
        cold_fans = FanSet()
        evap_fans = FanSet()
        self.store = store
        self.rooms = rooms
        self.compressors = Bank()
        self.supply = SupplyValve(store)
        self.temp = Collector(store)
        self.ammonia = Monitor(store)
        self.interlock = Interlock(store)
        self.cold_fans = cold_fans
        self.evap_fans = evap_fans
        self.evap = Condenser(store, evap_fans)
        self.defrost = Controller(cold_fans, rooms, store)
        self.load = LoadCalculator(store)
        self.accumulator = Accumulator(store)
        self.auditor = Auditor(store)
        self.scheduler = Scheduler(store)
