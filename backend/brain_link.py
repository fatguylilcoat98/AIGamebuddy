"""Talk to Chris's Buddy brain over the phone-call WebSocket.

The mic streams 16 kHz PCM up. Muse replies come back as one MP3 per sentence.
Nothing is spoken if the brain is missing or the socket is down, and no token
is ever written into the log.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import socket
import ssl
import struct
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from .hidden_process import detach_console
from .hidden_process import popen as hidden_popen
from .mouth_follow import MouthFollower, audio_level
from .native_guard import crashed, python_exe

log = logging.getLogger("buddy.brain")

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def brain_config_path() -> Path | None:
    override = (os.environ.get("BUDDY_BRAIN_CONFIG") or "").strip()
    if override:
        return Path(override)
    appdata = (os.environ.get("APPDATA") or "").strip()
    if not appdata and os.name == "nt":
        appdata = str(Path.home() / "AppData" / "Roaming")
    if not appdata:
        return None
    return Path(appdata) / "Buddy" / "brain.json"


def load_brain_config(path: Path | None = None) -> tuple[str, str]:
    """Return (websocket url, token). Empty strings when the file is absent."""
    chosen = path if path is not None else brain_config_path()
    if chosen is None or not chosen.is_file():
        return "", ""
    try:
        data = json.loads(chosen.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        log.warning("Could not read the brain config. Buddy will stay quiet. %s", exc)
        return "", ""
    if not isinstance(data, dict):
        log.warning("Brain config is not an object. Buddy will stay quiet.")
        return "", ""
    url = str(data.get("url") or "").strip()
    token = str(data.get("token") or "").strip()
    return _ws_url(url), token


def brain_attitude(personality: str) -> str:
    name = (personality or "").strip().lower()
    if name in {"casual", "regular", "friendly"}:
        return "friendly"
    if name == "extreme":
        return "extreme"
    if name == "sassy":
        return "sassy"
    return "friendly"


def _ws_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    if text.startswith("https://"):
        text = "wss://" + text[len("https://"):]
    elif text.startswith("http://"):
        text = "ws://" + text[len("http://"):]
    if "://" not in text:
        text = "wss://" + text
    parsed = urlparse(text)
    path = parsed.path or ""
    if path in {"", "/"}:
        path = "/ws"
    return parsed._replace(path=path).geturl()


class _Socket:
    def __init__(self, url: str, token: str, timeout: float = 12) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        secure = parsed.scheme == "wss"
        port = parsed.port or (443 if secure else 80)
        raw = socket.create_connection((host, port), timeout=timeout)
        if secure:
            context = ssl.create_default_context()
            raw = context.wrap_socket(raw, server_hostname=host)
        path = parsed.path or "/ws"
        if parsed.query:
            path = path + "?" + parsed.query
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host if not parsed.port else host + ':' + str(parsed.port)}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"X-Buddy-Token: {token}\r\n"
            "\r\n"
        )
        raw.sendall(request.encode("ascii"))
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = raw.recv(1)
            if not chunk:
                raise ConnectionError("brain closed during the handshake")
            header += chunk
            if len(header) > 8192:
                raise ConnectionError("brain handshake was too long")
        status = header.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise ConnectionError(status.decode("ascii", "replace"))
        accept = base64.b64encode(hashlib.sha1((key + _GUID).encode("ascii")).digest())
        if accept not in header:
            raise ConnectionError("brain handshake was not accepted")
        raw.settimeout(0.3)
        self._sock = raw
        self._buf = b""

    def send(self, payload: bytes, opcode: int) -> None:
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        header = bytes([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", length)
        self._sock.sendall(header + mask + masked)

    def send_text(self, obj: dict) -> None:
        self.send(json.dumps(obj).encode("utf-8"), 1)

    def send_binary(self, payload: bytes) -> None:
        self.send(payload, 2)

    def recv(self):
        # A TCP read can hold more than one frame. Deliver those before waiting again,
        # or the second sentence sits unplayed until the brain sends something else.
        frame = _take_frame(self._buf)
        if frame is not None:
            self._buf = frame[2]
            return frame[0], frame[1]
        try:
            chunk = self._sock.recv(65536)
        except socket.timeout:
            return None
        if not chunk:
            frame = _take_frame(self._buf)
            if frame is not None:
                self._buf = frame[2]
                return frame[0], frame[1]
            raise ConnectionError("brain closed the socket")
        self._buf += chunk
        frame = _take_frame(self._buf)
        if frame is None:
            return None
        self._buf = frame[2]
        return frame[0], frame[1]

    def close(self) -> None:
        try:
            self.send(b"", 8)
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass


def _take_frame(buf: bytes):
    if len(buf) < 2:
        return None
    length = buf[1] & 0x7F
    offset = 2
    if length == 126:
        if len(buf) < 4:
            return None
        length = struct.unpack("!H", buf[2:4])[0]
        offset = 4
    elif length == 127:
        if len(buf) < 10:
            return None
        length = struct.unpack("!Q", buf[2:10])[0]
        offset = 10
    if buf[1] & 0x80:
        if len(buf) < offset + 4 + length:
            return None
        mask = buf[offset:offset + 4]
        offset += 4
        data = bytes(byte ^ mask[index % 4] for index, byte in enumerate(buf[offset:offset + length]))
    else:
        if len(buf) < offset + length:
            return None
        data = buf[offset:offset + length]
    return buf[0] & 0x0F, data, buf[offset + length:]


LIMIT_KNEE = 0.6
LIMIT_CEILING = 0.89  # about -1 dBFS


def soft_limit(samples: list[float], knee: float = LIMIT_KNEE, ceiling: float = LIMIT_CEILING) -> list[float]:
    """Gentle limiter. Quiet samples pass untouched; loud peaks bend toward the ceiling."""
    import math
    span = max(1e-6, ceiling - knee)
    out = []
    for sample in samples:
        level = abs(sample)
        if level <= knee:
            out.append(sample)
            continue
        bent = knee + span * math.tanh((level - knee) / span)
        out.append(bent if sample >= 0 else -bent)
    return out


class SampleQueue:
    """One stream of float samples. Later sentences append. The tail is kept."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chunks: list[tuple[int, list[float]]] = []
        self._offset = 0
        self.last_rms = 0.0
        self._tail_until = 0.0

    def enqueue(self, seq: int, samples: list[float], gain: float) -> int:
        scaled = soft_limit([float(sample) * gain for sample in samples])
        if not scaled:
            return 0
        with self._lock:
            self._chunks.append((int(seq), scaled))
        return len(scaled)

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._offset = 0
        self.last_rms = 0.0

    def pending(self) -> int:
        with self._lock:
            total = 0
            for index, (_seq, chunk) in enumerate(self._chunks):
                start = self._offset if index == 0 else 0
                total += max(0, len(chunk) - start)
            return total

    def take(self, count: int) -> list[float]:
        out: list[float] = []
        with self._lock:
            while len(out) < count and self._chunks:
                _seq, chunk = self._chunks[0]
                start = self._offset
                piece = chunk[start:start + (count - len(out))]
                out.extend(piece)
                if start + len(piece) >= len(chunk):
                    self._chunks.pop(0)
                    self._offset = 0
                else:
                    self._offset = start + len(piece)
        if out:
            total = sum(sample * sample for sample in out)
            self.last_rms = (total / len(out)) ** 0.5
            self._tail_until = time.monotonic() + 0.4
        return out

    def busy(self) -> bool:
        return self.pending() > 0 or time.monotonic() < self._tail_until


class Speaker:
    """One output stream at the device's own rate. Sentences are already in the queue."""

    RATE = 24000

    def __init__(self, queue: SampleQueue) -> None:
        self.queue = queue
        self._stream = None
        self._stop = threading.Event()
        self._clock: threading.Thread | None = None
        self.rate = self.RATE
        self.underruns = 0
        self._logged_underruns = 0
        self._last_underrun_log = 0.0

    def native_rate(self) -> int:
        try:
            import sounddevice as sd
            info = sd.query_devices(kind="output")
            rate = int(round(float(info.get("default_samplerate") or 0)))
            if 8000 <= rate <= 192000:
                return rate
        except Exception:
            pass
        return self.RATE

    def start(self) -> None:
        if self._stream is not None or (self._clock is not None and self._clock.is_alive()):
            return
        try:
            import numpy as np
            import sounddevice as sd

            def callback(outdata, frames, _time_info, status):
                if status and getattr(status, "output_underflow", False):
                    self.underruns += 1
                samples = self.queue.take(int(frames))
                data = np.zeros(frames, dtype=np.float32)
                if samples:
                    data[:len(samples)] = samples
                outdata[:, 0] = data

            self.rate = self.native_rate()
            self._stream = sd.OutputStream(
                samplerate=self.rate, channels=1, dtype="float32", callback=callback,
                blocksize=int(self.rate * 0.04), latency="high",
            )
            self._stream.start()
            detach_console()
            latency = getattr(self._stream, "latency", None)
            log.info("Speaker stream is open at %s Hz (device rate), latency=%s.", self.rate, latency)
            return
        except Exception as exc:
            detach_console()
            self.rate = self.RATE
            log.warning("Speaker stream did not open. The queue still runs. %s", exc)
        self._clock = threading.Thread(target=self._tick, name="buddy-speaker-clock", daemon=True)
        self._clock.start()

    def report_underruns(self, now: float | None = None, force: bool = False) -> None:
        moment = time.monotonic() if now is None else now
        if self.underruns == self._logged_underruns:
            return
        if not force and moment - self._last_underrun_log < 10:
            return
        log.warning("Speaker underruns: %s new, %s total.", self.underruns - self._logged_underruns, self.underruns)
        self._logged_underruns = self.underruns
        self._last_underrun_log = moment

    def _tick(self) -> None:
        step = int(self.rate * 0.04)
        while not self._stop.is_set():
            self.queue.take(step)
            self._stop.wait(0.04)

    def stop(self) -> None:
        self._stop.set()
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.report_underruns(force=True)
        log.info("Speaker closed. Underruns this run: %s.", self.underruns)


def _s16le_to_float(payload: bytes) -> list[float]:
    if not payload:
        return []
    n = len(payload) // 2
    if n <= 0:
        return []
    import array
    raw = array.array("h")
    raw.frombytes(payload[: n * 2])
    if raw.itemsize != 2:
        return []
    scale = 1.0 / 32768.0
    return [sample * scale for sample in raw]

def decode_mp3(mp3: bytes) -> tuple[list[float], int]:
    """Decode one sentence in this process. No console, no extra python.exe."""
    import array
    import miniaudio
    decoded = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16)
    raw = decoded.samples
    if isinstance(raw, (bytes, bytearray)):
        samples = array.array("h")
        samples.frombytes(raw[:len(raw) - (len(raw) % 2)])
    else:
        samples = raw
    channels = int(decoded.nchannels or 1)
    if channels > 1:
        samples = samples[::channels]
    rate = int(decoded.sample_rate or Speaker.RATE)
    return [sample / 32768.0 for sample in samples], rate


def resample(samples: list[float], src: int, dst: int) -> list[float]:
    if not samples or src == dst or src <= 0:
        return samples
    count = max(1, int(round(len(samples) * float(dst) / float(src))))
    if count == len(samples):
        return samples
    import numpy as np
    old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    new = np.linspace(0.0, 1.0, num=count, endpoint=False)
    return np.interp(new, old, np.asarray(samples, dtype="float32")).astype("float32").tolist()


class BrainLink:
    """One call to the brain, started only while a game window is visible."""

    def __init__(self, session) -> None:
        self.session = session
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._want = False
        self._attitude = "friendly"
        self._url, self._token = load_brain_config()
        self._thread: threading.Thread | None = None
        self._sock: _Socket | None = None
        self._mic = None
        self._mic_chunks: list[bytes] = []
        self._logged_missing = False
        self._logged_down = False
        self._outbox: list[dict] = []
        self._clips: list[tuple[int, bytes]] = []
        self.follower = MouthFollower()
        self._audio_stop = threading.Event()
        self._cut_seq = 0
        self._out_seq = 0
        self._output = SampleQueue()
        self._speaker = Speaker(self._output)
        from .game_duck import GameDucker
        self.ducker = GameDucker()
        self.ducker.recover()
        self._player = threading.Thread(target=self._play_loop, name="buddy-brain-audio", daemon=True)
        self._player.start()
        self._mouth = threading.Thread(target=self._watch_audio, name="buddy-mouth", daemon=True)
        self._mouth.start()

    def configured(self) -> bool:
        return bool(self._url and self._token)

    def sync(self, visible: bool, attitude: str) -> None:
        self._attitude = attitude or "friendly"
        if not self.configured():
            if not self._logged_missing:
                self._logged_missing = True
                where = brain_config_path()
                log.info("No brain config at %s. Buddy will stay quiet.", where or "%APPDATA%\\Buddy\\brain.json")
            self._want = False
            return
        self._want = bool(visible)
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, name="buddy-brain", daemon=True)
                self._thread.start()

    def set_attitude(self, attitude: str) -> None:
        self._attitude = attitude or "friendly"
        self._queue({"type": "attitude", "attitude": self._attitude})

    def set_talk_settings(self, look_interval=None, frequency=None) -> None:
        message = {"type": "settings"}
        if look_interval is not None:
            message["look_interval"] = int(look_interval)
        if frequency is not None:
            message["frequency"] = str(frequency)
        self._queue(message)

    def push_game(self, text: str, react: bool, image: str = "") -> bool:
        cleaned = " ".join((text or "").split())[:400]
        picture = (image or "").strip()
        if picture and not picture.startswith("data:"):
            picture = "data:image/jpeg;base64," + picture
        if (not cleaned and not picture) or not self.configured() or not self._want:
            return False
        message = {"type": "game", "text": cleaned, "react": bool(react)}
        if picture:
            message["image"] = picture
        self._queue(message)
        log.info("Sent the screen to the brain (image=%s bytes, react=%s).", len(picture), bool(react))
        return True

    def close(self) -> None:
        self._want = False
        self._stop.set()
        self._audio_stop.set()
        self._hangup()
        self._speaker.stop()
        self.ducker.close()

    def _queue(self, message: dict) -> None:
        with self._lock:
            self._outbox.append(message)

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self._want:
                self._hangup()
                self._stop.wait(0.4)
                continue
            if self._sock is None:
                if not self._connect():
                    self._stop.wait(5)
                    continue
            try:
                self._pump()
            except Exception as exc:
                if not self._logged_down:
                    self._logged_down = True
                    log.warning("Brain is unreachable. Buddy will stay quiet. %s", exc)
                else:
                    log.info("Brain is still unreachable. Buddy is staying quiet.")
                self._hangup()
                self._stop.wait(5)

    def _connect(self) -> bool:
        try:
            sock = _Socket(self._url, self._token)
        except Exception as exc:
            if not self._logged_down:
                self._logged_down = True
                host = urlparse(self._url).hostname or "the brain"
                log.warning("Brain is unreachable at %s. Buddy will stay quiet. %s", host, exc)
            return False
        self._sock = sock
        self._logged_down = False
        log.info("Brain connected. Attitude is %s.", self._attitude)
        try:
            sock.send_text({
                "type": "hello",
                "attitude": self._attitude,
                "history": [],
                "look_interval": int(getattr(self.session, "look_interval", 10) or 10),
                "frequency": str(getattr(self.session, "frequency", "normal") or "normal"),
            })
        except Exception as exc:
            log.warning("Brain dropped the hello. Buddy will stay quiet. %s", exc)
            self._hangup()
            return False
        self._start_mic()
        return True

    def _start_mic(self) -> None:
        self._stop_mic()
        try:
            proc = hidden_popen(
                [python_exe(), "-m", "backend.pcm_mic"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            log.warning("Microphone is off. Buddy can still hear the brain, but not the room. %s", exc)
            self._mic = None
            return
        self._mic = proc
        log.info("Microphone is streaming to the brain.")

        def _read() -> None:
            stdout = proc.stdout
            if stdout is None:
                return
            while not self._stop.is_set() and proc.poll() is None:
                chunk = stdout.read(1280)
                if not chunk:
                    break
                with self._lock:
                    self._mic_chunks.append(chunk)
            code = proc.poll()
            if code not in (None, 0) and not self._stop.is_set():
                if crashed(code):
                    log.warning("Microphone is off. The listener crashed (code %s), so Buddy will not hear the room.", code)
                else:
                    log.warning("Microphone is off. The listener stopped, so Buddy will not hear the room.")

        threading.Thread(target=_read, name="buddy-brain-mic", daemon=True).start()

    def _stop_mic(self) -> None:
        proc = self._mic
        self._mic = None
        with self._lock:
            self._mic_chunks.clear()
        if proc is None:
            return
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass

    def _pump(self) -> None:
        sock = self._sock
        if sock is None:
            return
        self._flush()
        self._send_mic()
        incoming = sock.recv()
        if incoming is None:
            return
        opcode, payload = incoming
        if opcode == 8:
            raise ConnectionError("brain closed the call")
        if opcode == 9:
            sock.send(payload, 10)
            return
        if opcode == 1:
            self._on_text(payload)
        elif opcode == 2:
            self._on_audio(payload)

    def _flush(self) -> None:
        sock = self._sock
        if sock is None:
            return
        with self._lock:
            pending = list(self._outbox)
            self._outbox.clear()
        for message in pending:
            sock.send_text(message)

    def _send_mic(self) -> None:
        sock = self._sock
        if sock is None:
            return
        with self._lock:
            chunks = self._mic_chunks
            self._mic_chunks = []
        # Silence while Buddy's line is in the speaker, plus a 400 ms tail.
        # Game music and his own voice must not go up as if Chris were talking.
        if self._output.busy():
            for chunk in chunks:
                sock.send_binary(b"\x00" * len(chunk))
            return
        for chunk in chunks:
            sock.send_binary(chunk)

    def _send_play(self, on: bool, seq: int) -> None:
        self._queue({"type": "play", "on": bool(on), "seq": int(seq)})
        log.info("Play %s seq=%s", "on" if on else "off", int(seq))

    def _on_text(self, payload: bytes) -> None:
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return
        kind = message.get("type")
        if kind == "barge":
            self._cut_seq = int(message.get("seq") or 0)
            self._audio_stop.set()
            with self._lock:
                self._clips.clear()
            self._output.clear()
            log.info("Brain barge-in. Stopping the current line.")
        elif kind == "thinking":
            seq = int(message.get("seq") or 0)
            if not self._cut_seq or seq >= self._cut_seq:
                self._audio_stop.clear()
        elif kind in {"note", "end"}:
            text = str(message.get("text") or message.get("reason") or kind)
            log.info("Brain note: %s", text[:180])
        elif kind == "ready":
            log.info("Brain is ready.")

    def _on_audio(self, payload: bytes) -> None:
        if self.session.muted or self.session.volume <= 0:
            return
        if len(payload) < 4:
            return
        header_len = int.from_bytes(payload[:4], "little")
        if header_len < 2 or 4 + header_len > len(payload):
            return
        try:
            header = json.loads(payload[4:4 + header_len].decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            header = {}
        audio = payload[4 + header_len:]
        if not audio:
            return
        seq = int(header.get("seq") or 0)
        if self._audio_stop.is_set() and self._cut_seq and seq < self._cut_seq:
            return
        self._audio_stop.clear()
        fmt = str(header.get("fmt") or "mp3")
        if fmt == "s16le" and audio:
            rate = int(header.get("rate") or 24000)
            samples = _s16le_to_float(audio)
            if not samples:
                return
            self._speaker.start()
            samples = resample(samples, rate, self._speaker.rate)
            gain = max(0.0, min(1.0, float(self.session.volume) / 100.0))
            count = self._output.enqueue(seq, samples, gain)
            self._out_seq = seq
            log.info("Queued reply audio seq=%s samples=%s stream=1", seq, count)
            return
        with self._lock:
            self._clips.append((seq, audio))

    def _play_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                clip = self._clips.pop(0) if self._clips else None
            if clip is None:
                self._stop.wait(0.02)
                continue
            seq, mp3 = clip
            if self._audio_stop.is_set() and self._cut_seq and seq < self._cut_seq:
                continue
            try:
                samples, rate = decode_mp3(mp3)
            except Exception as exc:
                log.warning("Could not play a brain reply. Buddy will stay quiet. %s", exc)
                continue
            if self._audio_stop.is_set() and self._cut_seq and seq < self._cut_seq:
                continue
            self._speaker.start()
            samples = resample(samples, rate, self._speaker.rate)
            gain = max(0.0, min(1.0, float(self.session.volume) / 100.0))
            count = self._output.enqueue(seq, samples, gain)
            self._out_seq = seq
            log.info("Queued reply audio seq=%s samples=%s", seq, count)

    def _watch_audio(self) -> None:
        announced = None
        quiet_since = None
        while not self._stop.is_set():
            # The game drops about 11 dB while a line plays and comes back
            # after the 400 ms tail plus 350 ms more.
            if self._output.busy():
                quiet_since = None
                self.ducker.duck()
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since > 0.35:
                self.ducker.restore()
            self._speaker.report_underruns()
            pending = self._output.pending()
            seq = self._out_seq
            if pending and announced != seq:
                if announced is not None:
                    self._send_play(False, announced)
                self._send_play(True, seq)
                announced = seq
                self.session._brain_speaking = True
            elif pending and announced is not None:
                raw = max(0.0, min(1.0, (self._output.last_rms - 0.01) / 0.16))
                self.session.mouth = self.follower.step(raw, 0.04)
            elif announced is not None:
                self._send_play(False, announced)
                announced = None
                self.session._brain_speaking = False
                self.session.mouth = self.follower.step(0.0, 0.04)
            self._stop.wait(0.04)

    def _hangup(self) -> None:
        self._stop_mic()
        sock = self._sock
        self._sock = None
        if sock is not None:
            sock.close()
        self.session._brain_speaking = False


