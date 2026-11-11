"""How often Buddy looks at the game picture.

The choices are 5 seconds through 60 seconds, in steps of 5. Ten seconds is
the default. A look that is still running is not started again.
"""
from __future__ import annotations

LOOK_INTERVALS = tuple(range(5, 61, 5))
DEFAULT_LOOK_INTERVAL = 10


def normalize_look_interval(value) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LOOK_INTERVAL
    if seconds in LOOK_INTERVALS:
        return seconds
    return DEFAULT_LOOK_INTERVAL


def look_due(*, last: float, now: float, interval: int, busy: bool) -> str:
    """Return 'wait', 'skip', or 'look'."""
    if now - last < max(1, int(interval)):
        return "wait"
    if busy:
        return "skip"
    return "look"
