"""Connect foreground game detection to monitor capture (read-only).

Place beside game_session.py and screen_capture.py. This module does not
start the server or capture continuously. A caller requests each snapshot.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from game_session import current_session
from screen_capture import ScreenCapture


@dataclass(frozen=True)
class CaptureTarget:
    monitor_id: int
    window_title: str | None
    application: str | None
    is_known_emulator: bool
    window_rect: tuple[int, int, int, int] | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class GameCapture:
    """Select a monitor containing the foreground window, then capture it."""

    def __init__(self, capture: ScreenCapture | None = None):
        self.capture = capture if capture is not None else ScreenCapture()
        self._last_game_monitor: int | None = None

    def target(self, fallback_monitor: int = 1) -> CaptureTarget:
        monitors = self.capture.monitors()
        if not monitors:
            raise RuntimeError("No monitors available")
        session = current_session()
        monitor_ids = {monitor["id"] for monitor in monitors}
        if fallback_monitor not in monitor_ids:
            raise ValueError(f"Monitor {fallback_monitor} not found")

        selected = self._last_game_monitor if self._last_game_monitor in monitor_ids else fallback_monitor
        reason = "last_game_monitor" if self._last_game_monitor in monitor_ids else "fallback_monitor"
        if session.is_known_emulator and session.active_window and session.window_rect:
            left, top, right, bottom = session.window_rect
            if right > left and bottom > top:
                def overlap(monitor: dict) -> int:
                    x1 = max(left, monitor["left"])
                    y1 = max(top, monitor["top"])
                    x2 = min(right, monitor["left"] + monitor["width"])
                    y2 = min(bottom, monitor["top"] + monitor["height"])
                    return max(0, x2 - x1) * max(0, y2 - y1)

                best = max(monitors, key=overlap)
                if overlap(best) > 0:
                    selected = best["id"]
                    reason = "foreground_emulator_overlap"
                    self._last_game_monitor = selected

        return CaptureTarget(
            monitor_id=selected,
            window_title=session.title,
            application=session.application,
            is_known_emulator=session.is_known_emulator,
            window_rect=session.window_rect,
            reason=reason,
        )

    def snapshot(self, fallback_monitor: int = 1) -> tuple[CaptureTarget, bytes]:
        """Return (capture metadata, JPEG bytes) for one monitor snapshot.

        Captures the full selected monitor, not a cropped window. Callers
        should not infer that a detected emulator proves game identity.
        """
        target = self.target(fallback_monitor)
        return target, self.capture.jpeg(target.monitor_id)
