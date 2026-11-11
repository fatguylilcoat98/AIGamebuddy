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
import tempfile
import threading
import time
import wave
from pathlib import Path
from urllib.parse import urlparse

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
        try:
            chunk = self._sock.recv(65536)
        except socket.timeout:
            return None
        if not chunk:
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
        self._mic: subprocess.Popen | None = None
        self._mic_chunks: list[bytes] = []
        self._logged_missing = False
        self._logged_down = False
        self._last_game = ""
        self._outbox: list[dict] = []
        self._clips: list[bytes] = []
        self.follower = MouthFollower()
        self._audio_stop = threading.Event()
        self._player = threading.Thread(target=self._play_loop, name="buddy-brain-audio", daemon=True)
        self._player.start()

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

    def push_game(self, text: str, react: bool) -> bool:
        cleaned = " ".join((text or "").split())[:800]
        if not cleaned or not self.configured() or not self._want:
            return False
        if cleaned == self._last_game:
            return True
        self._last_game = cleaned
        self._queue({"type": "game", "text": cleaned, "react": bool(react)})
        log.info("Sent the screen to the brain (%s characters).", len(cleaned))
        return True

    def close(self) -> None:
        self._want = False
        self._stop.set()
        self._audio_stop.set()
        self._hangup()

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
            sock.send_text({"type": "hello", "attitude": self._attitude, "history": []})
        except Exception as exc:
            log.warning("Brain dropped the hello. Buddy will stay quiet. %s", exc)
            self._hangup()
            return False
        self._start_mic()
        return True

    def _start_mic(self) -> None:
        self._stop_mic()
        try:
            proc = subprocess.Popen(
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
        for chunk in chunks:
            sock.send_binary(chunk)

    def _on_text(self, payload: bytes) -> None:
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return
        kind = message.get("type")
        if kind == "barge":
            self._audio_stop.set()
            with self._lock:
                self._clips.clear()
            log.info("Brain barge-in. Stopping the current line.")
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
        audio = payload[4 + header_len:]
        if not audio:
            return
        with self._lock:
            self._clips.append(audio)

    def _play_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                clip = self._clips.pop(0) if self._clips else None
            if clip is None:
                self._stop.wait(0.05)
                continue
            self._play(clip)

    def _play(self, mp3: bytes) -> None:
        self.session._brain_speaking = True
        try:
            wav = _mp3_to_wav(mp3)
            if not wav or self._audio_stop.is_set():
                return
            _play_wav_level(wav, self.session.volume, self.session, self.follower, self._audio_stop)
        except Exception as exc:
            log.warning("Could not play a brain reply. Buddy will stay quiet. %s", exc)
        finally:
            self.session._brain_speaking = False
            if not self._audio_stop.is_set():
                self.session.mouth = 0.0

    def _hangup(self) -> None:
        self._stop_mic()
        sock = self._sock
        self._sock = None
        if sock is not None:
            sock.close()
        self.session._brain_speaking = False


def _mp3_to_wav(mp3: bytes) -> bytes | None:
    fd, src = tempfile.mkstemp(suffix=".mp3", prefix="buddy-brain-")
    os.close(fd)
    dest = src + ".wav"
    try:
        Path(src).write_bytes(mp3)
        code = (
            "import miniaudio, sys, wave\n"
            "decoded = miniaudio.decode_file(sys.argv[1], output_format=miniaudio.SampleFormat.SIGNED16)\n"
            "handle = wave.open(sys.argv[2], 'wb')\n"
            "handle.setnchannels(decoded.nchannels)\n"
            "handle.setsampwidth(2)\n"
            "handle.setframerate(decoded.sample_rate)\n"
            "handle.writeframes(decoded.samples)\n"
            "handle.close()\n"
        )
        done = subprocess.run(
            [python_exe(), "-c", code, src, dest],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if done.returncode != 0 or not Path(dest).is_file():
            log.warning("Neural voice decode failed. Buddy will stay quiet for this line.")
            return None
        return Path(dest).read_bytes()
    except Exception as exc:
        log.warning("Neural voice decode failed. Buddy will stay quiet for this line. %s", exc)
        return None
    finally:
        for path in (src, dest):
            try:
                os.remove(path)
            except OSError:
                pass


def _play_wav_level(wav_bytes: bytes, volume: int, session, follower: MouthFollower, stop: threading.Event) -> None:
    import array
    import io
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        rate = handle.getframerate() or 1
        channels = handle.getnchannels() or 1
        frames = handle.readframes(handle.getnframes())
    samples = array.array("h")
    samples.frombytes(frames[:len(frames) - (len(frames) % 2)])
    if channels > 1:
        samples = array.array("h", samples[::channels])
    gain = max(0.0, min(1.0, volume / 100.0))
    window = max(1, int(rate * 0.04))
    if os.name == "nt":
        import winsound
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="buddy-brain-play-")
        os.close(fd)
        try:
            Path(path).write_bytes(wav_bytes)
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            started = time.perf_counter()
            for index in range(0, len(samples), window):
                if stop.is_set():
                    winsound.PlaySound(None, winsound.SND_PURGE)
                    break
                chunk = samples[index:index + window]
                floats = [sample / 32768.0 * gain for sample in chunk]
                raw = audio_level(floats)
                now = time.perf_counter()
                dt = max(0.001, (index / rate) - (now - started))
                session.mouth = follower.step(raw, max(0.001, window / rate))
                time.sleep(dt if dt < 0.2 else window / rate)
            winsound.PlaySound(None, winsound.SND_PURGE)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        return
    # Off Windows the test run has no speaker. Still advance the mouth.
    for index in range(0, len(samples), window):
        if stop.is_set():
            break
        chunk = samples[index:index + window]
        floats = [sample / 32768.0 for sample in chunk]
        session.mouth = follower.step(audio_level(floats), window / rate)
