"""Detect the active game/emulator window on Windows (read-only).

No external packages or per-game ROM adapters required. This module does not
capture pixels or interact with game input. Window titles are only hints; they
are not proof of which game is running.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import asdict, dataclass

# Expand this list as needed; detection also returns unknown active windows.
EMULATORS = {
    "emulationstation.exe": "EmulationStation",
    "emulationstation-de.exe": "EmulationStation",
    "emulationstation-desktop-edition.exe": "EmulationStation",
    "snes9x.exe": "Snes9x",
    "retroarch.exe": "RetroArch",
    "dolphin.exe": "Dolphin",
    "pcsx2-qt.exe": "PCSX2",
    "duckstation-qt-x64-releaseLTCG.exe".lower(): "DuckStation",
    "duckstation.exe": "DuckStation",
    "mesen.exe": "Mesen",
    "project64.exe": "Project64",
    "mame.exe": "MAME",
    "ppssppwindows64.exe": "PPSSPP",
    "cemu.exe": "Cemu",
    "yuzu.exe": "Yuzu",
    "ryujinx.exe": "Ryujinx",
}


@dataclass(frozen=True)
class GameSession:
    supported_platform: bool
    active_window: bool
    title: str | None
    executable: str | None
    application: str | None
    is_known_emulator: bool
    window_rect: tuple[int, int, int, int] | None

    def to_dict(self) -> dict:
        return asdict(self)


def current_session() -> GameSession:
    """Return a snapshot of the foreground window; safe on non-Windows hosts."""
    empty = GameSession(os.name == "nt", False, None, None, None, False, None)
    if os.name != "nt":
        return empty

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return empty

    length = min(max(user32.GetWindowTextLengthW(hwnd), 0), 8192)
    title_buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
    title = title_buffer.value or None

    rect = wintypes.RECT()
    bounds = None
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        bounds = (rect.left, rect.top, rect.right, rect.bottom)

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    executable = None
    if pid.value:
        # PROCESS_QUERY_LIMITED_INFORMATION, compatible with modern Windows.
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if handle:
            try:
                buffer = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(buffer))
                if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    executable = os.path.basename(buffer.value).lower()
            finally:
                kernel32.CloseHandle(handle)

    application = EMULATORS.get(executable) if executable else None
    return GameSession(True, True, title, executable, application,
                       application is not None, bounds)


if __name__ == "__main__":
    import json
    print(json.dumps(current_session().to_dict(), indent=2))
