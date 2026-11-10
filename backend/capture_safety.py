"""Stops the overlay from capturing or resizing itself into a feedback loop.

Captured frames are for vision only. They are never drawn on the overlay.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("buddy.capture")

OVERLAY_SIZE = (1280, 720)
# Capture is on demand and at most this often. Never once per animation frame.
CAPTURE_INTERVAL_SECONDS = 1.0


def overlay_may_show_capture() -> bool:
    """The overlay paint path must not draw a screenshot. This stays false."""
    return False


def clamp_overlay_geometry(width: int, height: int, monitor: tuple[int, int] = (1920, 1080)) -> tuple[int, int]:
    """Fullscreen target is the monitor. A smaller size is the shrink bug, not a layout."""
    del width, height
    return int(monitor[0]), int(monitor[1])


def fit_frame(monitor: tuple[int, int], design: tuple[int, int] = OVERLAY_SIZE) -> tuple[int, int, int, int]:
    """Letterboxed 16:9 frame inside the monitor.

    1920x1080 is exactly 1.5 times the 1280x720 art, which is the 1080p metadata.
    Other sizes use the same uniform scale. A wider or taller monitor gets bars.
    """
    monitor_w, monitor_h = int(monitor[0]), int(monitor[1])
    design_w, design_h = design
    if monitor_w < 2 or monitor_h < 2:
        return 0, 0, design_w, design_h
    scale = min(monitor_w / design_w, monitor_h / design_h)
    frame_w = max(1, int(round(design_w * scale)))
    frame_h = max(1, int(round(design_h * scale)))
    if abs(monitor_w - 1920) <= 2 and abs(monitor_h - 1080) <= 2:
        frame_w, frame_h = 1920, 1080
    origin_x = max(0, (monitor_w - frame_w) // 2)
    origin_y = max(0, (monitor_h - frame_h) // 2)
    return origin_x, origin_y, frame_w, frame_h


def bgra_to_rgb(raw: bytes, width: int, height: int) -> bytes:
    """Turn a tightly packed BGRA buffer into RGB.

    mss grabs BGRA on Windows. Reading those bytes as RGB swaps red and blue
    and turns the blue hologram pink.
    """
    needed = width * height * 4
    if width <= 0 or height <= 0 or len(raw) < needed:
        raise ValueError(f"BGRA buffer is {len(raw)} bytes, expected at least {needed}")
    import numpy as np
    pixels = np.frombuffer(raw, dtype=np.uint8, count=needed).reshape((height, width, 4))
    return np.ascontiguousarray(pixels[:, :, [2, 1, 0]]).tobytes()


class SafetySwitch:
    """Disable capture and window moves after repeated errors or size changes."""

    def __init__(self) -> None:
        self.capture_enabled = True
        self.move_enabled = True
        self.reason = ""
        self._errors: list[float] = []
        self._sizes: list[tuple[tuple[int, int], float]] = []

    def disable(self, reason: str, *, quiet: bool = False) -> None:
        if self.capture_enabled or self.move_enabled:
            if quiet:
                log.info("Capture and window moves stopped: %s", reason)
            else:
                log.error("Safety stop: %s", reason)
        self.capture_enabled = False
        self.move_enabled = False
        self.reason = reason

    def note_error(self, message: str, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        self._errors = [stamp for stamp in self._errors if moment - stamp < 5]
        self._errors.append(moment)
        if len(self._errors) >= 3:
            self.disable(f"capture failed repeatedly: {message}")
            return True
        log.warning("Capture error: %s", message)
        return False

    def note_geometry(self, size: tuple[int, int], now: float | None = None,
                      design: tuple[int, int] = OVERLAY_SIZE) -> bool:
        if size == design:
            return False
        moment = time.monotonic() if now is None else now
        self._sizes = [(seen, stamp) for seen, stamp in self._sizes if moment - stamp < 5]
        if self._sizes and self._sizes[-1][0] == size:
            return False
        self._sizes.append((size, moment))
        shrunk = [seen for seen, _stamp in self._sizes if seen[0] < design[0] or seen[1] < design[1]]
        if len(shrunk) >= 3:
            self.disable(f"overlay geometry changed repeatedly ({size[0]}x{size[1]})")
            return True
        log.warning("Overlay size %sx%s is not %sx%s. Clamping.", size[0], size[1], design[0], design[1])
        return False

    def allow_capture(self, now: float, last_capture: float) -> bool:
        if not self.capture_enabled:
            return False
        return now - last_capture >= CAPTURE_INTERVAL_SECONDS
