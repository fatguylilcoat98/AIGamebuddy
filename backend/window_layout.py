"""Overlay and emulator window geometry.

Moving a real window is Windows-only. On any other system the call reports
that it did not move anything.
"""
from __future__ import annotations

import os

from .layout_spec import HOLE, OUTPUT_H, OUTPUT_W, scale_rect
from .results import ActionResult


def hole_on_screen(origin_x: int, origin_y: int, window_w: int, window_h: int) -> tuple[int, int, int, int]:
    x, y, w, h = scale_rect(HOLE, window_w, window_h)
    return origin_x + x, origin_y + y, w, h


def emulator_target(overlay_origin: tuple[int, int], overlay_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Screen rectangle where the emulator should sit so it fills the game opening."""
    return hole_on_screen(overlay_origin[0], overlay_origin[1], overlay_size[0], overlay_size[1])


def position_foreground_window(rect: tuple[int, int, int, int]) -> ActionResult:
    if os.name != "nt":
        return ActionResult(False, "Positioning the emulator window requires Windows, so I did not move it.",
                            reason="not_windows")
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ActionResult(False, "I do not see a foreground window, so I did not move one.",
                                reason="no_window")
        x, y, w, h = rect
        flags = 0x0040  # SWP_SHOWWINDOW
        moved = bool(user32.SetWindowPos(hwnd, 0, int(x), int(y), int(w), int(h), flags))
        if not moved:
            return ActionResult(False, "Windows refused to move the foreground window, so I left it where it was.",
                                reason="set_window_failed")
        return ActionResult(True, "Moved the foreground window into the game opening.",
                            reason="moved", data={"rect": [x, y, w, h]})
    except Exception as exc:
        return ActionResult(False, f"I could not move the window. {exc}", reason="window_error")


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
    return OUTPUT_W, OUTPUT_H
