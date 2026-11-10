"""How the player talks to Buddy.

Select and Start still reach the game, and Start pauses a Super NES game, so
Buddy does not listen on those. Hold the two shoulder buttons, or hold F9.
Open mic listens for "Hey Buddy" only when the local mic helper is installed.
"""
from __future__ import annotations

HOLD_SECONDS = 0.5


def shoulder_hold(was_down: bool, down: bool, held_for: float, step: float,
                  threshold: float = HOLD_SECONDS) -> tuple[list[str], float]:
    """Edge events for both shoulders held about half a second.

    Returns the events and the new held duration. `step` is how long since
    the last poll.
    """
    if not down:
        events = ["shoulders_talk_up"] if was_down or held_for > 0 else []
        return events, 0.0
    held = held_for + max(0.0, step)
    if held_for < threshold <= held:
        return ["shoulders_talk_down"], held
    return [], held


def is_wake_phrase(text: str) -> bool:
    cleaned = " ".join((text or "").lower().replace("'", "").split())
    return cleaned.startswith("hey buddy") or cleaned.startswith("hey, buddy")


def utterance_after_wake(text: str) -> str:
    """Words after Hey Buddy. Empty when that was the whole phrase."""
    cleaned = " ".join((text or "").strip().split())
    lower = cleaned.lower().replace("'", "")
    for prefix in ("hey buddy", "hey, buddy"):
        if lower.startswith(prefix):
            return cleaned[len(prefix):].strip(" ,.!?")
    return ""


def start_wake_listener(session, stopped) -> str:
    """Listen for Hey Buddy when the local mic helper is installed."""
    try:
        from .buddy_ears import BuddyEars
    except Exception:
        return "unavailable"
    if not BuddyEars.available():
        return "unavailable"

    def loop() -> None:
        import time
        ears = BuddyEars(max_seconds=4)
        while not stopped():
            if getattr(session, "talk_mode", "") != "wake" or getattr(session, "closed", False):
                time.sleep(0.4)
                continue
            try:
                ears.start()
                time.sleep(2.2)
                heard = ears.stop_and_transcribe()
            except Exception:
                time.sleep(1.0)
                continue
            text = getattr(heard, "text", "") or ""
            if not is_wake_phrase(text):
                continue
            follow = utterance_after_wake(text)
            if not follow:
                try:
                    ears.start()
                    time.sleep(3.0)
                    heard = ears.stop_and_transcribe()
                    follow = getattr(heard, "text", "") or ""
                except Exception:
                    follow = ""
            if follow:
                session.handle_text(follow)

    import threading
    threading.Thread(target=loop, name="buddy-wake", daemon=True).start()
    return "listening"


def read_shoulders_down(get_state) -> bool:
    """True when both shoulder buttons are down on the first pad that answers.

    `get_state(index, state) -> 0` is XInputGetState. Missing pads are skipped.
    """
    for index in range(4):
        state = get_state(index)
        if state is None:
            continue
        buttons = int(state)
        left = 0x0100
        right = 0x0200
        if buttons & left and buttons & right:
            return True
    return False
