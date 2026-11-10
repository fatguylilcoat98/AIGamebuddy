"""Speech output with volume, mute, device selection, and interruption.

Windows can synthesize with System.Speech into a WAV, then play that WAV on a
chosen output device. If the device is missing, nothing is played.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

from .results import ActionResult

_SYNTH_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.Rate = [int]$env:AIGAMEBUDDY_VOICE_RATE
    $path = $env:AIGAMEBUDDY_WAVE_PATH
    if ([string]::IsNullOrWhiteSpace($path)) { exit 2 }
    $synth.SetOutputToWaveFile($path)
    $message = [Console]::In.ReadToEnd()
    if (-not [string]::IsNullOrWhiteSpace($message)) {
        $synth.Speak($message)
    }
} finally {
    $synth.Dispose()
}
"""


@dataclass(frozen=True)
class AudioDevice:
    index: int | None
    name: str


def resolve_device(requested: str, devices: list[AudioDevice]) -> AudioDevice | None:
    cleaned = (requested or "").strip().lower()
    if not cleaned:
        return AudioDevice(None, "default")
    for device in devices:
        if device.name.lower() == cleaned or cleaned in device.name.lower():
            return device
    return None


def list_sounddevice_devices() -> list[AudioDevice]:
    try:
        import sounddevice as sd
        infos = sd.query_devices()
    except ImportError:
        return []
    except Exception as exc:
        # sounddevice imports, then query_devices raises OSError when PortAudio is missing.
        logging.getLogger("buddy.audio").warning("Could not list audio devices: %s", exc)
        return []
    found = []
    for index, info in enumerate(infos):
        if info.get("max_output_channels", 0) > 0:
            found.append(AudioDevice(index, str(info.get("name") or f"device {index}")))
    return found


def neural_voice(character: str) -> str:
    """Microsoft neural voices. Male and female follow Buddy's character setting."""
    if str(character or "").lower() == "female":
        return "en-US-JennyNeural"
    return "en-US-GuyNeural"


def synthesize_edge_wav(text: str, character: str = "male") -> bytes | None:
    """Natural speech. Returns WAV bytes, or None when the network voice is unavailable."""
    try:
        import asyncio
        import edge_tts
        import miniaudio
    except ImportError:
        return None
    fd, mp3_path = tempfile.mkstemp(suffix=".mp3", prefix="buddy-voice-")
    os.close(fd)
    wav_path = ""
    try:
        async def _save() -> None:
            await edge_tts.Communicate(text[:1500], neural_voice(character)).save(mp3_path)
        asyncio.run(_save())
        if not Path(mp3_path).exists() or Path(mp3_path).stat().st_size < 64:
            return None
        decoded = miniaudio.decode_file(mp3_path, output_format=miniaudio.SampleFormat.SIGNED16)
        wav_fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="buddy-voice-")
        os.close(wav_fd)
        with wave.open(wav_path, "wb") as handle:
            handle.setnchannels(decoded.nchannels)
            handle.setsampwidth(2)
            handle.setframerate(decoded.sample_rate)
            handle.writeframes(decoded.samples)
        return Path(wav_path).read_bytes()
    except Exception as exc:
        logging.getLogger("buddy.audio").info("Neural voice unavailable, falling back. %s", exc)
        return None
    finally:
        for leftover in (mp3_path, wav_path):
            if leftover:
                try:
                    os.remove(leftover)
                except OSError:
                    pass


def synthesize_windows_wav(text: str, rate: int) -> bytes | None:
    if sys.platform != "win32":
        return None
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="buddy-voice-")
    os.close(fd)
    env = os.environ.copy()
    env["AIGAMEBUDDY_VOICE_RATE"] = str(max(-10, min(10, int(rate))))
    env["AIGAMEBUDDY_WAVE_PATH"] = path
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SYNTH_SCRIPT],
            input=text[:1500],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=60,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not Path(path).exists() or Path(path).stat().st_size < 44:
            return None
        return Path(path).read_bytes()
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _rms(samples) -> float:
    if len(samples) == 0:
        return 0.0
    import numpy as np
    value = float(np.sqrt(np.mean(np.square(samples))))
    return max(0.0, min(1.0, value * 4))


def play_wav_sounddevice(wav_bytes: bytes, volume: float, device: AudioDevice | None,
                         on_level) -> None:
    import numpy as np
    import sounddevice as sd
    import io
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
        width = handle.getsampwidth()
    if width == 2:
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    else:
        raise RuntimeError(f"Unsupported WAV sample width {width}")
    if channels > 1:
        samples = samples.reshape(-1, channels)
    gain = max(0.0, min(1.0, volume / 100.0))
    samples = samples * gain
    index = None if device is None or device.index is None else device.index
    sd.play(samples, rate, device=index)
    chunk = max(1, int(rate * 0.05))
    flat = samples if getattr(samples, "ndim", 1) == 1 else samples.mean(axis=1)
    for start in range(0, len(flat), chunk):
        if on_level:
            on_level(_rms(flat[start:start + chunk]))
        sd.sleep(50)
    sd.wait()
    if on_level:
        on_level(0.0)


class AudioOutput:
    def __init__(self, *, synthesizer=None, player=None, device_lister=None):
        self.character = "male"
        self.synthesizer = synthesizer or self._synthesize
        self.player = player or play_wav_sounddevice
        self.device_lister = device_lister or list_sounddevice_devices
        self._lock = threading.Lock()
        self.playing = False
        self._stop = False

    def stop(self) -> None:
        self._stop = True
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    @property
    def speaking(self) -> bool:
        with self._lock:
            return self.playing

    def devices(self) -> list[dict]:
        return [{"index": device.index, "name": device.name} for device in self.device_lister()]

    def _synthesize(self, text: str, rate: int) -> bytes | None:
        neural = synthesize_edge_wav(text, self.character)
        if neural:
            return neural
        return synthesize_windows_wav(text, rate)

    def speak(self, text: str, *, volume: int, rate: int, device_name: str, mute: bool,
              on_level=None, character: str = "male") -> ActionResult:
        self.character = character if character in {"male", "female"} else "male"
        try:
            return self._speak(text, volume=volume, rate=rate, device_name=device_name, mute=mute, on_level=on_level)
        except Exception as exc:
            logging.getLogger("buddy.audio").warning("speak failed: %s", exc)
            if on_level:
                try:
                    on_level(0.0)
                except Exception:
                    pass
            with self._lock:
                self.playing = False
            return ActionResult(
                False,
                f"Audio playback failed, so I did not finish speaking. {exc}",
                reason="playback_failed",
            )

    def _speak(self, text: str, *, volume: int, rate: int, device_name: str, mute: bool,
               on_level=None) -> ActionResult:
        if not text.strip():
            return ActionResult(False, "There was no line to speak.", reason="empty")
        if mute or volume <= 0:
            return ActionResult(False, "Audio is muted, so I did not speak that aloud.", reason="muted")
        devices = self.device_lister()
        device = resolve_device(device_name, devices)
        if device_name.strip() and device is None:
            names = ", ".join(item.name for item in devices) or "(none found)"
            return ActionResult(
                False,
                f"Output device '{device_name}' was not found, so I did not play audio. Devices: {names}",
                reason="device_missing",
            )
        wav = self.synthesizer(text, rate)
        if not wav:
            return ActionResult(
                False,
                "Text-to-speech is not available on this system, so I did not speak aloud.",
                reason="tts_unavailable",
            )
        self._stop = False
        with self._lock:
            self.playing = True
        try:
            self.player(wav, volume, device, on_level)
        except Exception as exc:
            logging.getLogger("buddy.audio").warning("Audio playback failed: %s", exc)
            return ActionResult(False, f"Audio playback failed, so I did not finish speaking. {exc}",
                                reason="playback_failed")
        finally:
            with self._lock:
                self.playing = False
            if on_level:
                on_level(0.0)
        device_label = device.name if device else "default"
        return ActionResult(True, f"Played audio on {device_label}.", reason="played",
                            data={"device": device_label})
