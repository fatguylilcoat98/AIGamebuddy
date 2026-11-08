"""Neural speech output for Game Buddy on Windows (Edge TTS).

Uses edge-tts for synthesis and Windows MediaPlayer for playback.
Speech is queued in a background worker. Stop interrupts playback.
Install: python -m pip install edge-tts
"""
from __future__ import annotations

import asyncio
import os
import queue
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from typing import Optional

import edge_tts

VOICE = os.getenv("AIGAMEBUDDY_EDGE_VOICE", "en-US-GuyNeural")
_PLAY_SCRIPT = r"""
Add-Type -AssemblyName PresentationCore
$p = New-Object System.Windows.Media.MediaPlayer
try {
    $p.Open([Uri]$env:AIGAMEBUDDY_AUDIO_FILE)
    $p.Volume = [double]$env:AIGAMEBUDDY_AUDIO_VOLUME
    $p.Play()
    $deadline = (Get-Date).AddSeconds(10)
    while (-not $p.NaturalDuration.HasTimeSpan -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 50
    }
    if (-not $p.NaturalDuration.HasTimeSpan) { throw 'Audio could not be loaded' }
    $duration = $p.NaturalDuration.TimeSpan.TotalMilliseconds
    $end = (Get-Date).AddMilliseconds($duration + 1000)
    while ((Get-Date) -lt $end) {
        Start-Sleep -Milliseconds 75
    }
} finally {
    $p.Stop()
    $p.Close()
}
"""


@dataclass(frozen=True)
class VoiceStatus:
    speaking: bool
    queued: int
    available: bool


class BuddyVoice:
    def __init__(self, *, rate: int = 0, volume: int = 100, voice_name: str = "") -> None:
        self.rate = max(-10, min(10, int(rate)))
        self.volume = max(0, min(100, int(volume)))
        self.voice_name = voice_name or VOICE
        self._queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=3)
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._speaking = False
        self._closed = False
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._worker, name="buddy-voice", daemon=True)
        self._thread.start()

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32"

    def speak(self, text: str, *, interrupt: bool = False) -> bool:
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
        self._cancel.set()
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
            audio_path = None
            try:
                if line is None:
                    return
                with self._lock:
                    if self._closed:
                        return
                    self._speaking = True
                self._cancel.clear()
                fd, audio_path = tempfile.mkstemp(suffix=".mp3", prefix="gamebuddy_")
                os.close(fd)
                rate = f"{self.rate * 5:+d}%"
                async def generate() -> None:
                    await edge_tts.Communicate(line, self.voice_name, rate=rate).save(audio_path)
                asyncio.run(generate())
                if self._cancel.is_set():
                    continue
                env = os.environ.copy()
                env["AIGAMEBUDDY_AUDIO_FILE"] = audio_path
                env["AIGAMEBUDDY_AUDIO_VOLUME"] = str(self.volume / 100)
                proc = subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PLAY_SCRIPT],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                with self._lock:
                    self._process = proc
                if self._cancel.is_set():
                    proc.kill()
                try:
                    proc.wait(timeout=100)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                finally:
                    with self._lock:
                        self._process = None
            except Exception:
                # Speech errors must never crash gameplay.
                pass
            finally:
                if audio_path:
                    try:
                        os.unlink(audio_path)
                    except OSError:
                        pass
                with self._lock:
                    self._speaking = False
                self._queue.task_done()


if __name__ == "__main__":
    voice = BuddyVoice()
    if not voice.available():
        raise SystemExit("BuddyVoice requires Windows")
    voice.speak("Hey, I'm Buddy. Let's catch some fish!")
    voice._queue.join()
    voice.shutdown()
