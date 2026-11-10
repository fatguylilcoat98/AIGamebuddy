"""Overlay and emulator window geometry.

Moving a real window is Windows-only. On any other system the call reports
that it did not move anything. Buddy never moves its own window: that shrinks
the overlay into its own game hole and looks like an infinite mirror.
"""
from __future__ import annotations

import logging
import os

from .capture_safety import OVERLAY_SIZE, clamp_overlay_geometry
from .game_session import EMULATORS
from .layout_spec import HOLE, OUTPUT_H, OUTPUT_W, scale_rect
from .results import ActionResult

log = logging.getLogger("buddy.layout")

# Win10 2004+. Hides the window from screen capture.
WDA_EXCLUDEFROMCAPTURE = 0x00000011
# Older fallback: capture shows a black rectangle instead of the window.
WDA_MONITOR = 0x00000001


def hole_on_screen(origin_x: int, origin_y: int, window_w: int, window_h: int) -> tuple[int, int, int, int]:
    x, y, w, h = scale_rect(HOLE, window_w, window_h)
    return origin_x + x, origin_y + y, w, h


def emulator_target(overlay_origin: tuple[int, int], overlay_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Screen rectangle where the emulator should sit so it fills the game opening."""
    return hole_on_screen(overlay_origin[0], overlay_origin[1], overlay_size[0], overlay_size[1])


def select_emulator_hwnd(windows: list[tuple[int, str]], own_hwnds: set[int]) -> int | None:
    """Pick a RetroArch or EmulationStation window. Never one of Buddy's own."""
    for hwnd, executable in windows:
        if not hwnd or int(hwnd) in own_hwnds:
            continue
        name = (executable or "").lower()
        if name in EMULATORS or "retroarch" in name or "emulationstation" in name:
            return int(hwnd)
    return None


def position_hwnd(hwnd: int, rect: tuple[int, int, int, int], own_hwnds: set[int] | None = None) -> ActionResult:
    """Move one known emulator window. Refuses Buddy's hwnd even if it is in front."""
    if os.name != "nt":
        return ActionResult(False, "Positioning the emulator window requires Windows, so I did not move it.",
                            reason="not_windows")
    forbidden = own_hwnds or set()
    if not hwnd or int(hwnd) in forbidden:
        return ActionResult(
            False,
            "That window is Buddy's overlay, so I did not move it.",
            reason="own_window",
        )
    return _set_window_pos(int(hwnd), rect)


def position_foreground_window(rect: tuple[int, int, int, int]) -> ActionResult:
    """Old entry point. It no longer moves whatever happens to be in front.

    Moving the foreground window pulled Buddy into its own hole, then other apps.
    """
    if os.name != "nt":
        return ActionResult(False, "Positioning the emulator window requires Windows, so I did not move it.",
                            reason="not_windows")
    return ActionResult(
        False,
        "I did not move the foreground window. Only a RetroArch or EmulationStation window can be placed.",
        reason="foreground_refused",
    )


def _set_window_pos(hwnd: int, rect: tuple[int, int, int, int]) -> ActionResult:
    try:
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        x, y, w, h = rect
        flags = 0x0040  # SWP_SHOWWINDOW
        moved = bool(user32.SetWindowPos(hwnd, 0, int(x), int(y), int(w), int(h), flags))
        if not moved:
            return ActionResult(False, "Windows refused to move the emulator window, so I left it where it was.",
                                reason="set_window_failed")
        return ActionResult(True, "Moved the emulator window into the game opening.",
                            reason="moved", data={"rect": [x, y, w, h], "hwnd": hwnd})
    except Exception as exc:
        return ActionResult(False, f"I could not move the window. {exc}", reason="window_error")


def list_toplevel_windows() -> list[tuple[int, str]]:
    """(hwnd, executable) for visible top-level windows. Empty off Windows."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        found: list[tuple[int, str]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            executable = ""
            if pid.value:
                handle = kernel32.OpenProcess(0x1000, False, pid.value)
                if handle:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = wintypes.DWORD(len(buffer))
                        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                            executable = os.path.basename(buffer.value).lower()
                    finally:
                        kernel32.CloseHandle(handle)
            found.append((int(hwnd), executable))
            return True

        user32.EnumWindows(visit, 0)
        return found
    except Exception as exc:
        log.warning("Could not list windows: %s", exc)
        return []


def exclude_window_from_capture(hwnd: int) -> str:
    """Keep this window out of screenshots. Returns the affinity that stuck."""
    if os.name != "nt" or not hwnd:
        return "not_windows"
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
        if user32.SetWindowDisplayAffinity(int(hwnd), WDA_EXCLUDEFROMCAPTURE):
            return "exclude"
        log.warning(
            "SetWindowDisplayAffinity WDA_EXCLUDEFROMCAPTURE failed on hwnd %s (error %s). Trying WDA_MONITOR.",
            hwnd, ctypes.get_last_error(),
        )
        if user32.SetWindowDisplayAffinity(int(hwnd), WDA_MONITOR):
            return "monitor"
        log.warning(
            "SetWindowDisplayAffinity WDA_MONITOR also failed on hwnd %s (error %s).",
            hwnd, ctypes.get_last_error(),
        )
        return "failed"
    except Exception as exc:
        log.warning("Could not exclude hwnd %s from capture: %s", hwnd, exc)
        return "failed"


def apply_hole_region(hwnd: int, width: int, height: int, hole: tuple[int, int, int, int]) -> ActionResult:
    """Cut the game opening out of a window so clicks pass through. Windows only."""
    if os.name != "nt":
        return ActionResult(False, "Click-through overlay holes require Windows.", reason="not_windows")
    try:
        import ctypes
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        full = gdi32.CreateRectRgn(0, 0, int(width), int(height))
        hx, hy, hw, hh = hole
        cut = gdi32.CreateRectRgn(int(hx), int(hy), int(hx + hw), int(hy + hh))
        gdi32.CombineRgn(full, full, cut, 4)  # RGN_DIFF
        gdi32.DeleteObject(cut)
        if not user32.SetWindowRgn(hwnd, full, True):
            return ActionResult(False, "Windows did not apply the overlay hole.", reason="region_failed")
        return ActionResult(True, "Overlay hole is click-through.", reason="region_set")
    except Exception as exc:
        return ActionResult(False, f"I could not cut the overlay hole. {exc}", reason="region_error")


def design_size() -> tuple[int, int]:
    return OVERLAY_SIZE if OVERLAY_SIZE else (OUTPUT_W, OUTPUT_H)
