"""Turn the game down while Buddy talks, then put it back.

This uses the game's own volume in the Windows mixer (its audio session), so
nothing is drawn on the game and the exact level comes back afterward.
RetroArch's VOLUME_DOWN network command was not used because it pops a
volume bar on top of the game every step.

If Buddy stops while the game is turned down, a small state file remembers the
real level and the next start puts it back.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("buddy.duck")

DUCK_DB = 11.0
DUCK_RAMP_S = 0.12
RESTORE_RAMP_S = 0.30
GAME_EXES = ("retroarch.exe",)


def db_to_gain(db: float) -> float:
    return float(10.0 ** (-abs(float(db)) / 20.0))


def ramp(start: float, end: float, steps: int) -> list[float]:
    steps = max(1, int(steps))
    return [start + (end - start) * (index + 1) / steps for index in range(steps)]


class GameDucker:
    """duck() and restore() return at once. A worker thread does the mixer calls.

    `backend` returns a list of (key, get_volume, set_volume) for the game's
    audio sessions. The real one is Windows Core Audio.
    """

    def __init__(self, backend: Optional[Callable[[], list]] = None, *, db: float = DUCK_DB,
                 state_path: Optional[Path] = None, sleep=time.sleep) -> None:
        self._backend = backend if backend is not None else _windows_sessions
        self.gain = db_to_gain(db)
        self.db = abs(float(db))
        self._state_path = state_path if state_path is not None else _default_state_path()
        self._sleep = sleep
        self._want = False
        self._ducked: dict = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.ducks = 0
        self.restores = 0
        self._recover = False
        self._apply_lock = threading.Lock()

    # --- public -----------------------------------------------------------
    def duck(self) -> None:
        if self._want:
            return
        self._want = True
        self._kick()

    def restore(self) -> None:
        if not self._want and not self._ducked:
            return
        self._want = False
        self._kick()

    def close(self) -> None:
        self._want = False
        try:
            self.apply()
        except Exception as exc:
            log.warning("Could not put the game volume back on exit. %s", exc)
        self._stop.set()
        self._wake.set()

    def recover(self) -> None:
        """Put back a level left turned down by a run that did not finish. Non-blocking."""
        path = self._state_path
        if path is None or not path.is_file():
            return
        self._recover = True
        self._kick()

    def recover_now(self) -> None:
        path = self._state_path
        if path is None or not path.is_file():
            return
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            level = float(saved.get("volume", 1.0))
        except Exception:
            level = 1.0
        fixed = 0
        try:
            for _key, _get, setter in self._backend():
                setter(max(0.0, min(1.0, level)))
                _release(setter)
                fixed += 1
        except Exception as exc:
            log.info("Game volume recovery skipped. %s", exc)
            return
        if fixed:
            log.info("Game volume put back to %.2f after an unfinished duck (%s session(s)).", level, fixed)
            self._clear_state()

    # --- worker -----------------------------------------------------------
    def _kick(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="buddy-duck", daemon=True)
                self._thread.start()
        self._wake.set()

    def _run(self) -> None:
        com = _com_init()
        try:
            while not self._stop.is_set():
                self._wake.wait(1.0)
                self._wake.clear()
                if self._stop.is_set():
                    break
                if self._recover:
                    self._recover = False
                    self.recover_now()
                try:
                    self.apply()
                except Exception as exc:
                    log.warning("Game ducking failed. The game volume was left alone. %s", exc)
        finally:
            _com_done(com)

    def apply(self) -> None:
        """Make the mixer match what was asked. Called on the worker thread."""
        with self._apply_lock:
            self._apply()

    def _apply(self) -> None:
        if self._want and not self._ducked:
            sessions = self._backend()
            if not sessions:
                return
            plan = []
            for key, getter, setter in sessions:
                try:
                    before = float(getter())
                except Exception:
                    continue
                plan.append((key, before, setter))
            if not plan:
                return
            self._write_state(max(before for _k, before, _s in plan))
            steps = max(1, int(DUCK_RAMP_S / 0.02))
            for level in ramp(1.0, self.gain, steps):
                for _key, before, setter in plan:
                    setter(before * level)
                self._sleep(DUCK_RAMP_S / steps)
            self._ducked = {key: (before, setter) for key, before, setter in plan}
            self.ducks += 1
            log.info("Game ducked -%.0f dB while Buddy talks (%s session(s), was %.2f).",
                     self.db, len(plan), max(before for _k, before, _s in plan))
        elif not self._want and self._ducked:
            held = self._ducked
            self._ducked = {}
            steps = max(1, int(RESTORE_RAMP_S / 0.02))
            for level in ramp(self.gain, 1.0, steps):
                for _key, (before, setter) in held.items():
                    try:
                        setter(before * level)
                    except Exception:
                        pass
                self._sleep(RESTORE_RAMP_S / steps)
            for _key, (before, setter) in held.items():
                try:
                    setter(before)
                except Exception:
                    pass
                _release(setter)
            self._clear_state()
            self.restores += 1
            log.info("Game volume restored to %.2f.", max(before for before, _s in held.values()))

    def _write_state(self, level: float) -> None:
        path = self._state_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"volume": round(float(level), 4)}), encoding="utf-8")
        except OSError:
            pass

    def _clear_state(self) -> None:
        path = self._state_path
        if path is None:
            return
        try:
            path.unlink()
        except OSError:
            pass


def _release(setter) -> None:
    done = getattr(setter, "release", None)
    if done is not None:
        try:
            done()
        except Exception:
            pass


def _default_state_path() -> Optional[Path]:
    base = (os.environ.get("LOCALAPPDATA") or "").strip()
    if not base:
        return None
    return Path(base) / "Buddy" / "game-duck.json"


# --- Windows Core Audio through ctypes -----------------------------------

def _com_init():
    if os.name != "nt":
        return None
    try:
        import ctypes
        ole32 = ctypes.WinDLL("ole32")
        hr = ole32.CoInitializeEx(None, 0x0)  # COINIT_MULTITHREADED
        return ole32 if hr in (0, 1) else None
    except Exception:
        return None


def _com_done(ole32) -> None:
    if ole32 is not None:
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


def _exe_name(pid: int) -> str:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    handle = kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(handle)


def _windows_sessions(exes: tuple = GAME_EXES) -> list:
    """(key, get, set) for every render session owned by the game, on every active output."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p, wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16),
                    ("d", ctypes.c_ubyte * 8)]

    def guid(text: str) -> GUID:
        import uuid
        raw = uuid.UUID(text).bytes_le
        out = GUID()
        ctypes.memmove(byref(out), raw, 16)
        return out

    def method(ptr, index: int, *argtypes):
        vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, *argtypes)
        fn = proto(vtable[index])
        return lambda *args: fn(ptr, *args)

    def release(ptr) -> None:
        if ptr:
            method(ptr, 2)()

    ole32 = ctypes.WinDLL("ole32")
    clsid = guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
    iid_enum = guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
    iid_mgr2 = guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")
    iid_ctl2 = guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D")
    iid_vol = guid("87CE5498-68D6-44E5-9215-6DA47EF883D8")

    enumerator = c_void_p()
    hr = ole32.CoCreateInstance(byref(clsid), None, 0x17, byref(iid_enum), byref(enumerator))
    if hr != 0 or not enumerator:
        raise OSError(f"MMDeviceEnumerator hr=0x{hr & 0xffffffff:08x}")
    found = []
    seen = set()
    try:
        collection = c_void_p()
        # eRender, DEVICE_STATE_ACTIVE
        if method(enumerator.value, 3, c_int, wintypes.DWORD, POINTER(c_void_p))(0, 1, byref(collection)) != 0:
            return []
        try:
            count = c_uint()
            method(collection.value, 3, POINTER(c_uint))(byref(count))
            for index in range(count.value):
                device = c_void_p()
                if method(collection.value, 4, c_uint, POINTER(c_void_p))(index, byref(device)) != 0:
                    continue
                try:
                    manager = c_void_p()
                    if method(device.value, 3, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p))(
                            byref(iid_mgr2), 0x17, None, byref(manager)) != 0:
                        continue
                    try:
                        sessions = c_void_p()
                        if method(manager.value, 5, POINTER(c_void_p))(byref(sessions)) != 0:
                            continue
                        try:
                            total = c_int()
                            method(sessions.value, 3, POINTER(c_int))(byref(total))
                            for number in range(total.value):
                                control = c_void_p()
                                if method(sessions.value, 4, c_int, POINTER(c_void_p))(number, byref(control)) != 0:
                                    continue
                                try:
                                    control2 = c_void_p()
                                    if method(control.value, 0, POINTER(GUID), POINTER(c_void_p))(
                                            byref(iid_ctl2), byref(control2)) != 0:
                                        continue
                                    try:
                                        pid = wintypes.DWORD()
                                        method(control2.value, 14, POINTER(wintypes.DWORD))(byref(pid))
                                        if not pid.value or _exe_name(pid.value) not in exes:
                                            continue
                                        volume = c_void_p()
                                        if method(control.value, 0, POINTER(GUID), POINTER(c_void_p))(
                                                byref(iid_vol), byref(volume)) != 0:
                                            continue
                                    finally:
                                        release(control2.value)
                                    key = (index, number, int(pid.value))
                                    if key in seen:
                                        release(volume.value)
                                        continue
                                    seen.add(key)
                                    found.append((key, volume.value))
                                finally:
                                    release(control.value)
                        finally:
                            release(sessions.value)
                    finally:
                        release(manager.value)
                finally:
                    release(device.value)
        finally:
            release(collection.value)
    finally:
        release(enumerator.value)

    out = []
    for key, ptr in found:
        def getter(ptr=ptr):
            level = c_float()
            hr = method(ptr, 4, POINTER(c_float))(byref(level))
            if hr != 0:
                raise OSError(f"GetMasterVolume hr=0x{hr & 0xffffffff:08x}")
            return float(level.value)

        def setter(value, ptr=ptr):
            method(ptr, 3, c_float, c_void_p)(c_float(max(0.0, min(1.0, float(value)))), None)

        setter.release = lambda ptr=ptr: release(ptr)

        out.append((key, getter, setter))
    # Each ISimpleAudioVolume is released after its restore. A fresh list is
    # taken on every duck, so a restarted game is found again.
    return out
