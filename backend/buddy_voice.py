"""Windows text-to-speech output for AIGamebuddy.

Uses Windows' built-in System.Speech synthesizer; no API key or pip package.
Call BuddyVoice.speak() with a completed line of dialogue. Speech runs in a
background thread so the game and backend stay responsive.
"""
from __future__ import annotations

import os
import queue
import subprocess

from .hidden_process import popen as hidden_popen
import sys
import threading
from dataclasses import dataclass
from typing import Optional


# PowerShell reads the line from standard input, never from interpolated code.
# This avoids quoting/injection issues with arbitrary AI-generated dialogue.
_SPEAK_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.Rate = [int]$env:AIGAMEBUDDY_VOICE_RATE
    $synth.Volume = [int]$env:AIGAMEBUDDY_VOICE_VOLUME
    $requested = $env:AIGAMEBUDDY_VOICE_NAME
    if ($requested) {
        try { $synth.SelectVoice($requested) } catch { }
    }
    $message = [Console]::In.ReadToEnd()
    if (-not [string]::IsNullOrWhiteSpace($message)) {
        $synth.Speak($message)
    }
} finally {
    $synth.Dispose()
}
"""


@dataclass(frozen=True)
class VoiceStatus:
    speaking: bool
    queued: int
    available: bool


class BuddyVoice:
    """Non-blocking Windows TTS with interruption and a bounded queue.

    Example:
        voice = BuddyVoice(rate=1, volume=90)
        voice.speak("Nice catch!")
        # Later, on app exit:
        voice.shutdown()
    """

    def __init__(self, *, rate: int = 0, volume: int = 100, voice_name: str = "") -> None:
        self.rate = max(-10, min(10, int(rate)))
        self.volume = max(0, min(100, int(volume)))
        self.voice_name = voice_name
        self._queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=3)
        self._lock = threading.Lock()
        self._process = None
        self._speaking = False
        self._closed = False
        self._thread = threading.Thread(target=self._worker, name="buddy-voice", daemon=True)
        self._thread.start()

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32"

    def speak(self, text: str, *, interrupt: bool = False) -> bool:
        """Queue speech; return False if unavailable, closed, or queue full.

        `interrupt=True` cancels the current line and clears pending speech.
        """
        if not self.available() or not isinstance(text, str) or not text.strip():
            return False
        with self._lock:
            if self._closed:
                return False
        if interrupt:
            self.stop()
        try:
            self._queue.put_nowait(text.strip()[:1500])
            return True
        except queue.Full:
            return False

    def stop(self) -> None:
        """Stop current speech and discard pending lines."""
        with self._lock:
            proc = self._process
            if proc is not None and proc.poll() is None:
                proc.kill()
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def status(self) -> VoiceStatus:
        with self._lock:
            speaking = self._speaking
        return VoiceStatus(speaking=speaking, queued=self._queue.qsize(), available=self.available())

    def shutdown(self) -> None:
        """Stop speaking and close the worker (safe to call more than once)."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.stop()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=2)

    def _worker(self) -> None:
        while True:
            line = self._queue.get()
            try:
                if line is None:
                    return
                with self._lock:
                    if self._closed:
                        return
                    self._speaking = True
                env = os.environ.copy()
                env.update({
                    "AIGAMEBUDDY_VOICE_RATE": str(self.rate),
                    "AIGAMEBUDDY_VOICE_VOLUME": str(self.volume),
                    "AIGAMEBUDDY_VOICE_NAME": self.voice_name,
                })
                # PowerShell is installed with supported Windows versions.
                proc = hidden_popen(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SPEAK_SCRIPT],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    env=env,
                )
                with self._lock:
                    self._process = proc
                try:
                    proc.communicate(input=line, timeout=90)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                finally:
                    with self._lock:
                        self._process = None
            except (OSError, ValueError):
                # Voice failure must not crash gameplay or the backend.
                pass
            finally:
                with self._lock:
                    self._speaking = False
                self._queue.task_done()


if __name__ == "__main__":
    voice = BuddyVoice()
    if not voice.available():
        print("BuddyVoice requires Windows.")
        raise SystemExit(1)
    print("Speaking a test line...")
    voice.speak("Hey, I'm Buddy. Let's play!")
    voice._queue.join()
    voice.shutdown()
