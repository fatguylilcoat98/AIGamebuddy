"""A noise floor for a room with a game on.

Game music is steady. A person talking is louder than that bed for a stretch.
Buddy's own speaker is not measured here: the call drops the mic while he talks.
"""
from __future__ import annotations

from collections import deque

FRAME_MS = 20
# A barge, and any turn, needs this much audio above the floor.
VOICED_MS = 350
VOICED_FRAMES = VOICED_MS // FRAME_MS  # 17 -> use 18 below
STREAK_FRAMES = 18  # 360 ms
BED_FRAMES = 15  # 300 ms, so a new music level is adopted before a barge can fire
GATE_RATIO = 2.6

HALLU = {
    "you", "thank you", "thanks for watching", "thank you for watching",
    "bye", "uh", "um", "hmm", "mm", "oh",
    "im sorry", "i am sorry", "sorry", "about to be gone",
}


class RoomEar:
    """Decide when the mic has a person, not the game."""

    def __init__(self) -> None:
        self.recent: deque[float] = deque(maxlen=BED_FRAMES)
        self.pending: list[float] = []
        self.floor = 180.0
        self.streak = 0
        self.gated = False

    def gate_level(self) -> float:
        return max(160.0, self.floor * GATE_RATIO)

    def _recompute(self) -> None:
        if not self.recent:
            return
        ordered = sorted(self.recent)
        self.floor = ordered[len(ordered) // 2]

    def frame(self, rms: float, vad_speech: bool) -> str | None:
        """One 20 ms frame. 'speech_start' only after sustained loud speech."""
        if self.gated:
            self.streak = 0
            self.pending.clear()
            return None
        level = float(rms)
        voiced = bool(vad_speech) and level > self.gate_level()
        if not voiced:
            self.recent.append(level)
            self._recompute()
            self.streak = 0
            self.pending.clear()
            return None
        self.streak += 1
        self.pending.append(level)
        # A steady rise is the game getting louder, not a person.
        if self.streak == 12 and self.pending:
            lo, hi = min(self.pending), max(self.pending)
            if lo > 0 and hi < lo * 1.35:
                self.floor = sum(self.pending) / len(self.pending)
                self.recent.clear()
                self.recent.extend(self.pending[-BED_FRAMES:])
                self.pending.clear()
                self.streak = 0
                return None
        if self.streak >= STREAK_FRAMES:
            self.streak = 0
            self.pending.clear()
            return "speech_start"
        return None


def normalize_heard(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum() or ch == " ").strip()


def keep_transcript(text: str, voiced_ms: int, no_speech_prob: float, avg_logprob: float) -> bool:
    """Drop a whisper guess that is tiny or unsure. Music produces those."""
    norm = normalize_heard(text)
    words = [word for word in norm.split() if word]
    if not words or norm in HALLU:
        return False
    if no_speech_prob > 0.5 or avg_logprob < -0.9:
        return False
    if voiced_ms < VOICED_MS:
        return False
    if len(words) <= 2 and voiced_ms < 500:
        return False
    return True
