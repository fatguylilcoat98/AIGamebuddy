"""AIGamebuddy's commentary gate: decide WHEN Buddy may speak.

No API calls, microphone access, or speech playback here. The voice/dialogue
layer will supply an actual line later. Keep one BuddyBrain instance alive
for the duration of a gaming session.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import time


@dataclass(frozen=True)
class BrainDecision:
    should_speak: bool
    reason: str
    event: str
    priority: int

    def to_dict(self) -> dict:
        return {
            "should_speak": self.should_speak,
            "reason": self.reason,
            "event": self.event,
            "priority": self.priority,
        }


class BuddyBrain:
    """Rate-limit spontaneous commentary and avoid repetitive observations.

    Priorities: 0 = background, 1 = ordinary, 2 = notable, 3 = major.
    A direct player request can bypass cooldown, but never interrupts speech.
    """

    def __init__(self, cooldown_seconds: float = 25.0,
                 repeat_window_seconds: float = 120.0):
        if cooldown_seconds < 0 or repeat_window_seconds < 0:
            raise ValueError("Timing windows cannot be negative")
        self.cooldown_seconds = cooldown_seconds
        self.repeat_window_seconds = repeat_window_seconds
        self._last_spoken_at: float | None = None
        self._recent: list[tuple[float, str]] = []

    def decide(self, event: str, priority: int = 1, *,
               player_speaking: bool = False,
               buddy_speaking: bool = False,
               direct_request: bool = False,
               now: float | None = None) -> BrainDecision:
        """Decide whether to generate a line. Call mark_spoken only after playback.

        `now` defaults to a monotonic clock; injectable for repeatable tests.
        `event` should be a short observation, e.g. a vision description.
        """
        if priority not in (0, 1, 2, 3):
            raise ValueError("priority must be 0, 1, 2, or 3")
        current = time.monotonic() if now is None else now
        normalized = " ".join(event.lower().split())
        if not normalized:
            return BrainDecision(False, "empty_event", event, priority)
        if buddy_speaking:
            return BrainDecision(False, "buddy_already_speaking", event, priority)
        if player_speaking and not direct_request:
            return BrainDecision(False, "player_speaking", event, priority)
        if direct_request:
            return BrainDecision(True, "player_requested", event, priority)
        if priority == 0:
            return BrainDecision(False, "background_event", event, priority)

        self._recent = [(t, s) for t, s in self._recent
                        if 0 <= current - t < self.repeat_window_seconds]
        if any(SequenceMatcher(None, normalized, previous).ratio() >= 0.85
               for _, previous in self._recent):
            return BrainDecision(False, "repeated_observation", event, priority)

        if self._last_spoken_at is not None:
            elapsed = current - self._last_spoken_at
            # Major moments can break the ordinary cooldown after 5 seconds.
            required_wait = min(5.0, self.cooldown_seconds) if priority == 3 else self.cooldown_seconds
            if elapsed < required_wait:
                return BrainDecision(False, "cooldown", event, priority)
        return BrainDecision(True, "ready", event, priority)

    def mark_spoken(self, event: str, *, now: float | None = None) -> None:
        """Call after Buddy actually starts speaking, not after decide()."""
        current = time.monotonic() if now is None else now
        normalized = " ".join(event.lower().split())
        if not normalized:
            return
        self._last_spoken_at = current
        self._recent.append((current, normalized))
        self._recent = [(t, s) for t, s in self._recent
                        if 0 <= current - t < self.repeat_window_seconds]

    def reset(self) -> None:
        """Clear timing when a new game session begins."""
        self._last_spoken_at = None
        self._recent.clear()
