"""Capture the game window only.

The full desktop includes Buddy's overlay. Grabbing it and showing it again
is the infinite-mirror loop. If RetroArch or EmulationStation is not open,
this captures nothing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .screen_capture import ScreenCapture
from .window_layout import list_toplevel_windows, select_emulator_hwnd


@dataclass(frozen=True)
class CaptureTarget:
    monitor_id: int
    window_title: str | None
    application: str | None
    is_known_emulator: bool
    window_rect: tuple[int, int, int, int] | None
    reason: str
    hwnd: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class GameCapture:
    """Capture one emulator window. Never the whole monitor."""

    def __init__(self, capture: ScreenCapture | None = None, own_hwnds: set[int] | None = None):
        self.capture = capture if capture is not None else ScreenCapture()
        self.own_hwnds = own_hwnds or set()

    def locate(self, windows: list[tuple[int, str]] | None = None) -> CaptureTarget | None:
        listed = list_toplevel_windows() if windows is None else windows
        hwnd = select_emulator_hwnd(listed, self.own_hwnds)
        if hwnd is None:
            return None
        executable = ""
        for candidate, exe in listed:
            if int(candidate) == int(hwnd):
                executable = exe
                break
        rect = _window_rect(hwnd)
        if rect is None:
            return None
        return CaptureTarget(
            monitor_id=0,
            window_title=None,
            application=executable or "emulator",
            is_known_emulator=True,
            window_rect=rect,
            reason="emulator_window",
            hwnd=int(hwnd),
        )

    def snapshot(self, fallback_monitor: int = 1, windows: list[tuple[int, str]] | None = None):
        """Return (target, jpeg) or None when there is no game window.

        `fallback_monitor` is ignored. A missing game is not a reason to grab
        the desktop.
        """
        del fallback_monitor
        target = self.locate(windows)
        if target is None or not target.window_rect:
            return None
        left, top, right, bottom = target.window_rect
        width = right - left
        height = bottom - top
        jpeg = self.capture.jpeg_rect((left, top, width, height))
        return target, jpeg


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    import os
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        rect = wintypes.RECT()
        if not user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None
