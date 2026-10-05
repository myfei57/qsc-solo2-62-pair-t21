"""Safety interlock that latches on a trip."""

from .interlock import Interlock, Trip
from .report import InterlockState

__all__ = ["Interlock", "InterlockState", "Trip"]
