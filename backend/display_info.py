"""Per-monitor pixels for the overlay window.

Windows must be told we want real pixels before Tk starts. Otherwise a
125% or 150% desktop reports a smaller screen and the window covers only
part of the monitor.
"""
from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger("buddy.display")

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
_PER_MONITOR_V2 = -4


def enable_per_monitor_dpi() -> str:
    """Ask Windows for physical pixels. Safe to call more than once."""
    if os.name != "nt":
        return "not_windows"
    import ctypes
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(_PER_MONITOR_V2)):
            log.info("DPI awareness: per-monitor v2")
            return "per_monitor_v2"
    except Exception as exc:
        log.warning("SetProcessDpiAwarenessContext failed: %s", exc)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        log.info("DPI awareness: per-monitor")
        return "per_monitor"
    except Exception as exc:
        log.warning("SetProcessDpiAwareness(2) failed: %s", exc)
    try:
        user32.SetProcessDPIAware()
        log.info("DPI awareness: system")
        return "system"
    except Exception as exc:
        log.warning("SetProcessDPIAware failed: %s", exc)
        return "unchanged"


def monitor_rect(hwnd: int = 0) -> dict | None:
    """Physical pixels of the monitor nearest `hwnd`, or the primary monitor."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, ctypes.c_ulong]
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = ctypes.c_bool
    nearest = 2
    primary = 1
    monitor = user32.MonitorFromWindow(int(hwnd or 0), nearest if hwnd else primary)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    rect = info.rcMonitor
    dpi = _monitor_dpi(monitor)
    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
        "width": int(rect.right - rect.left),
        "height": int(rect.bottom - rect.top),
        "dpi": dpi,
    }


def _monitor_dpi(monitor) -> int:
    try:
        import ctypes
        x = ctypes.c_uint()
        y = ctypes.c_uint()
        # MDT_EFFECTIVE_DPI = 0
        hr = ctypes.windll.shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(x), ctypes.byref(y))
        if hr == 0 and x.value:
            return int(x.value)
    except Exception:
        pass
    return 96


def window_covers_monitor(window: dict, monitor: dict, tolerance: int = 8) -> bool:
    """True when the window rectangle covers the monitor, within a few pixels."""
    return (
        window["left"] <= monitor["left"] + tolerance
        and window["top"] <= monitor["top"] + tolerance
        and window["right"] >= monitor["right"] - tolerance
        and window["bottom"] >= monitor["bottom"] - tolerance
    )


def hole_screen_rect(frame_screen: dict, monitor: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Game hole in physical screen pixels.

    `monitor` is (left, top, width, height). The 1280x720 screen rect is scaled
    with the same letterbox transform as the overlay art.
    """
    from .capture_safety import fit_frame
    left, top, width, height = monitor
    origin_x, origin_y, frame_w, frame_h = fit_frame((width, height))
    sx = frame_w / 1280
    sy = frame_h / 720
    return (
        int(left + origin_x + round(frame_screen["x"] * sx)),
        int(top + origin_y + round(frame_screen["y"] * sy)),
        int(round(frame_screen["width"] * sx)),
        int(round(frame_screen["height"] * sy)),
    )


def describe_startup(requested: str, actual: dict, monitor: dict | None) -> str:
    dpi = monitor["dpi"] if monitor else "n/a"
    rect = (
        f"{monitor['left']},{monitor['top']} {monitor['width']}x{monitor['height']}"
        if monitor else "unknown"
    )
    text = (
        f"monitor rect={rect} dpi={dpi} requested={requested} "
        f"actual={actual['left']},{actual['top']} {actual['width']}x{actual['height']}"
    )
    if monitor and not window_covers_monitor(actual, monitor):
        text += " WARNING: window does not cover the monitor"
    return text
