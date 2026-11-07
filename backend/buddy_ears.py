"""Microphone input and local speech recognition for AIGamebuddy (Windows).

Install when ready to test: pip install sounddevice numpy faster-whisper

Push-to-talk usage:
    ears = BuddyEars()
    ears.start()                 # call on key-down
    ...
    result = ears.stop_and_transcribe()  # call on key-up
    if result.text:
        reply = dialogue.reply(player_text=result.text)

No microphone is opened until start(). Audio is processed locally and is not
uploaded. Model downloads may occur on the first transcription unless you
point WHISPER_MODEL at an already downloaded model directory.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import threading
from typing import Any, Optional


@dataclass(frozen=True)
class HeardSpeech:
    text: str
    duration_seconds: float
    error: str = ""


class BuddyEars:
    """Push-to-talk microphone capture and offline Whisper transcription.

    Call start() on press and stop_and_transcribe() on release. The latter is
    blocking: run it on a worker thread so the game UI remains responsive.
    """

    def __init__(self, *, sample_rate: int = 16000, device: Optional[int] = None,
                 model_name: Optional[str] = None, max_seconds: float = 30.0):
        self.sample_rate = int(sample_rate)
        self.device = device
        self.model_name = model_name or os.getenv("BUDDY_WHISPER_MODEL", "base.en")
        self.max_seconds = max(1.0, min(120.0, float(max_seconds)))
        self._lock = threading.Lock()
        self._chunks: list[Any] = []
        self._stream: Any = None
        self._frames = 0
        self._model: Any = None
        self._transcribe_lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        try:
            import numpy  # noqa: F401
            import sounddevice  # noqa: F401
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def devices() -> list[dict[str, Any]]:
        """List microphone devices. Requires sounddevice."""
        import sounddevice as sd
        return [dict(index=i, name=d["name"], channels=d["max_input_channels"])
                for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]

    @property
    def recording(self) -> bool:
        with self._lock:
            return self._stream is not None

    def start(self) -> None:
        """Begin recording. Raises if already recording or microphone unavailable."""
        import sounddevice as sd
        with self._lock:
            if self._stream is not None:
                raise RuntimeError("Microphone is already recording")
            self._chunks = []
            self._frames = 0
            limit = int(self.max_seconds * self.sample_rate)

            def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
                del time_info, status
                with self._lock:
                    remaining = limit - self._frames
                    if remaining > 0:
                        keep = min(frames, remaining)
                        self._chunks.append(indata[:keep, 0].copy())
                        self._frames += keep

            stream = sd.InputStream(samplerate=self.sample_rate, channels=1,
                                    dtype="float32", device=self.device,
                                    callback=callback)
            self._stream = stream
        try:
            stream.start()
        except Exception:
            with self._lock:
                self._stream = None
            stream.close()
            raise

    def stop(self) -> tuple[Any, float]:
        """Stop recording and return (float32 mono samples, seconds)."""
        import numpy as np
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is None:
            raise RuntimeError("Microphone is not recording")
        stream.stop()
        stream.close()
        with self._lock:
            samples = np.concatenate(self._chunks) if self._chunks else np.empty(0, dtype=np.float32)
            self._chunks = []
            self._frames = 0
        return samples, len(samples) / self.sample_rate

    def stop_and_transcribe(self) -> HeardSpeech:
        """Transcribe the current recording locally. Can take several seconds."""
        samples, duration = self.stop()
        if duration < 0.25:
            return HeardSpeech("", duration)
        try:
            from faster_whisper import WhisperModel
            with self._transcribe_lock:
                if self._model is None:
                    self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                segments, _ = self._model.transcribe(samples, language="en",
                                                      vad_filter=True, beam_size=1)
                text = " ".join(s.text.strip() for s in segments).strip()
            return HeardSpeech(text, duration)
        except Exception as exc:
            return HeardSpeech("", duration, f"Speech recognition failed: {exc}")

    def cancel(self) -> None:
        """Discard an active recording without transcribing it."""
        with self._lock:
            stream = self._stream
            self._stream = None
            self._chunks = []
            self._frames = 0
        if stream is not None:
            stream.stop()
            stream.close()
