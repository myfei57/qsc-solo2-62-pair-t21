"""Clock used when a defrost warm up is recorded."""

from __future__ import annotations

import time


def now_unix() -> int:
    """Current wall clock time in whole seconds."""

    return int(time.time())
