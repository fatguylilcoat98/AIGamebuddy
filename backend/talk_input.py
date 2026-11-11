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
    """Listen in a child process so a Whisper or PortAudio crash cannot kill Buddy."""
    import logging
    log = logging.getLogger("buddy.ears")

    def loop() -> None:
        import subprocess
        import time
        from .native_guard import crashed, probe, python_exe
        if probe("microphone", "import sounddevice") != "ok" or probe("whisper", "import faster_whisper") != "ok":
            log.warning("Microphone is off. The speech library did not load, so Buddy will not listen.")
            return
        misses = 0
        while not stopped() and not getattr(session, "closed", False):
            if getattr(getattr(session, "audio", None), "speaking", False):
                time.sleep(0.3)
                continue
            try:
                done = subprocess.run(
                    [python_exe(), "-m", "backend.mic_worker", "2.2"],
                    capture_output=True, text=True, timeout=40, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.warning("Microphone is off. The listener did not finish. %s", exc)
                return
            if crashed(done.returncode):
                log.warning(
                    "Microphone is off. The listener crashed (code %s), so Buddy will not listen.",
                    done.returncode,
                )
                return
            if done.returncode != 0:
                misses += 1
                detail = ((done.stderr or "") + (done.stdout or "")).strip()
                log.warning("Microphone listen failed. %s", detail[-300:])
                if misses >= 2:
                    log.warning("Microphone is off. Listening failed twice, so Buddy will not listen.")
                    return
                time.sleep(1.0)
                continue
            misses = 0
            text = " ".join((done.stdout or "").split())
            if text.startswith("ERROR"):
                continue
            if is_wake_phrase(text):
                text = utterance_after_wake(text) or text
            if text:
                try:
                    session.handle_text(text)
                except Exception:
                    log.exception("Could not handle what the microphone heard")

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
