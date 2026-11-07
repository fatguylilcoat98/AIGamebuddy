"""AIGamebuddy session controller: coordinate existing backend components.

Nothing runs automatically on import. Call observe() when the player enables
vision, start_talking()/finish_talking() for push-to-talk, and close() on exit.
No continuous capture, background polling, or automatic microphone access.
Place beside buddy_brain.py, buddy_dialogue.py, buddy_voice.py, buddy_ears.py,
and vision_service.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from buddy_brain import BuddyBrain
from buddy_dialogue import BuddyDialogue


@dataclass(frozen=True)
class BuddyResponse:
    text: str = ""
    spoken: bool = False
    reason: str = ""
    observation: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class BuddyController:
    """One instance per gaming session. Public operations are synchronous.

    Transcription and vision calls may take seconds; invoke finish_talking()
    and observe() from a worker thread, never from a game's UI thread.
    """

    def __init__(self, *, personality: str = "sassy", vision_enabled: bool = False,
                 speech_enabled: bool = True, cooldown_seconds: float = 25.0):
        self.brain = BuddyBrain(cooldown_seconds=cooldown_seconds)
        self.dialogue = BuddyDialogue(personality=personality)
        self.vision_enabled = bool(vision_enabled)
        self.speech_enabled = bool(speech_enabled)
        self._voice: Any = None
        self._ears: Any = None
        self._vision: Any = None
        self._last_observation = ""
        self._lock = Lock()
        self._closed = False

    def _say(self, text: str) -> bool:
        if not text or not self.speech_enabled:
            return False
        if self._voice is None:
            from buddy_voice import BuddyVoice
            self._voice = BuddyVoice()
        return bool(self._voice.speak(text))

    def _speaking(self) -> bool:
        if self._voice is None:
            return False
        status = self._voice.status()
        return bool(status.speaking or status.queued)

    def observe(self, *, priority: int = 1, question: str = "What is happening in this game?") -> BuddyResponse:
        """Explicitly inspect one screenshot and optionally make a comment.

        Requires vision_enabled=True and BUDDY_VISION_API_KEY/MODEL configured.
        Caller controls frequency and must have consent to capture the screen.
        """
        with self._lock:
            if self._closed:
                return BuddyResponse(reason="closed")
            if not self.vision_enabled:
                return BuddyResponse(reason="vision_disabled")
            if self._ears is not None and self._ears.recording:
                return BuddyResponse(reason="player_speaking")
            try:
                if self._vision is None:
                    from vision_service import VisionService
                    self._vision = VisionService()
                result = self._vision.analyze(question=question)
                observation = result.description.strip()
                self._last_observation = observation
                decision = self.brain.decide(observation, priority=priority,
                                             buddy_speaking=self._speaking())
                if not decision.should_speak:
                    return BuddyResponse(reason=decision.reason, observation=observation)
                line = self.dialogue.reply(game_observation=observation,
                                           event=observation, spontaneous=True)
                spoken = self._say(line)
                if spoken:
                    self.brain.mark_spoken(observation)
                return BuddyResponse(text=line, spoken=spoken, reason="commentary",
                                     observation=observation)
            except Exception as exc:
                return BuddyResponse(reason="vision_error", error=str(exc))

    def start_talking(self) -> None:
        """Call on push-to-talk key-down; microphone starts only here."""
        with self._lock:
            if self._closed:
                raise RuntimeError("BuddyController is closed")
            if self._ears is None:
                from buddy_ears import BuddyEars
                self._ears = BuddyEars()
            if self._voice is not None:
                self._voice.stop()
            self._ears.start()

    def finish_talking(self) -> BuddyResponse:
        """Call on key-up; blocks while local speech recognition runs."""
        with self._lock:
            if self._closed or self._ears is None or not self._ears.recording:
                return BuddyResponse(reason="not_recording")
            heard = self._ears.stop_and_transcribe()
            if heard.error:
                return BuddyResponse(reason="transcription_error", error=heard.error)
            return self._reply_to_player(heard.text)

    def say_to_buddy(self, text: str) -> BuddyResponse:
        """Text alternative to the microphone; useful for testing."""
        with self._lock:
            if self._closed:
                return BuddyResponse(reason="closed")
            return self._reply_to_player(text)

    def _reply_to_player(self, text: str) -> BuddyResponse:
        text = text.strip()
        if not text:
            return BuddyResponse(reason="empty_speech")
        try:
            reply = self.dialogue.reply(player_text=text,
                                        game_observation=self._last_observation)
            spoken = self._say(reply)
            return BuddyResponse(text=reply, spoken=spoken, reason="player_reply")
        except Exception as exc:
            return BuddyResponse(reason="dialogue_error", error=str(exc))

    def close(self) -> None:
        """Release microphone and speech resources. Safe to call twice."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._ears is not None:
                self._ears.cancel()
            if self._voice is not None:
                self._voice.shutdown()
