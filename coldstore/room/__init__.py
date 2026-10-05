"""Cold rooms and their equipment assignments."""

from .report import RoomState, RoomView, validate_zone
from .room import Room, RoomRegistry

__all__ = ["Room", "RoomRegistry", "RoomState", "RoomView", "validate_zone"]
