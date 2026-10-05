"""Defrost controller.

Every defrost follows the same sequence: the cold air fan stops first, then
the warm up is recorded against the room. The command queue is persisted so an
interrupted console can replay or discard pending work.
"""

from __future__ import annotations

from coldstore.fan import FanSet
from coldstore.room import RoomRegistry
from coldstore.store.commands import append_command, clear_commands, load_commands
from coldstore.store.store import Store

from .report import DefrostState
from .schedule import now_unix

COMMAND_KEY = "defrost:commands"
WARMUP_KEY_PREFIX = "defrost:warmup:"
SPILL_KEY = "defrost:spill"


class Controller:
    """Sequences defrost steps against the cold fans and rooms."""

    def __init__(self, fans: FanSet, rooms: RoomRegistry, store: Store) -> None:
        self._fans = fans
        self._rooms = rooms
        self._store = store

    def start(self, room_id: str) -> None:
        """Stop the fan first and only then begin the warm up."""

        self._fans.stop_all()
        self._warm(room_id)
        self._rooms.set_defrosting(room_id, True)

    def _warm(self, room_id: str) -> None:
        if self._fans.running_ids():
            self._store.put(SPILL_KEY, "true")
        self._store.put(f"{WARMUP_KEY_PREFIX}{room_id}", str(now_unix()))

    def finish(self, room_id: str) -> None:
        """End the defrost and hand duty back to the primary fan."""

        self._rooms.set_defrosting(room_id, False)
        primary = self._fans.primary()
        if primary:
            self._fans.start(primary)

    def enqueue(self, room_id: str) -> None:
        append_command(self._store, COMMAND_KEY, room_id)

    def replay(self) -> list[str]:
        """Re-run every queued defrost in the order it was written."""

        commands = self.command_list()
        for room_id in commands:
            self.start(room_id)
        return commands

    def recover(self) -> None:
        """Discard defrost commands left over from an interrupted console."""

        clear_commands(self._store, COMMAND_KEY)

    def command_list(self) -> list[str]:
        return load_commands(self._store, COMMAND_KEY)

    def pending_count(self) -> int:
        return len(self.command_list())

    def select(self, zone: int) -> str:
        """Resolve the room that currently occupies a zone."""

        mapping = self._rooms.mapping()
        if zone not in mapping:
            raise ValueError(f"no cold room for zone {zone}")
        return mapping[zone]

    def defrosting(self) -> list[str]:
        return self._rooms.defrosting_ids()

    def warmups(self) -> list[str]:
        warmups: list[str] = []
        for key in self._store.keys():
            if key.startswith(WARMUP_KEY_PREFIX):
                warmups.append(key[len(WARMUP_KEY_PREFIX) :])
        return warmups

    def warmup_count(self) -> int:
        return len(self.warmups())

    def last_warmup(self) -> str | None:
        warmups = self.warmups()
        if not warmups:
            return None
        return warmups[-1]

    def spilled(self) -> bool:
        """True when a warm up was recorded while a fan was still running."""

        return self._store.get(SPILL_KEY)[1]

    def state(self) -> DefrostState:
        return DefrostState(
            commands=self.command_list(),
            warmups=self.warmups(),
            defrosting=self.defrosting(),
        )

    def describe(self) -> str:
        state = self.state()
        return (
            f"defrost commands={len(state.commands)} warmups={len(state.warmups)} "
            f"active={len(state.defrosting)}"
        )
