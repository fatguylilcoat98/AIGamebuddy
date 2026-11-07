"""Prepare captured game frames for a future AI vision provider.

No network calls, API keys, or background recording. Each call handles one
snapshot and returns JPEG bytes plus truthful capture metadata.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from PIL import Image, ImageOps, UnidentifiedImageError

from game_capture import GameCapture


@dataclass(frozen=True)
class VisionFrame:
    jpeg: bytes
    monitor_id: int
    window_title: str | None
    application: str | None
    width: int
    height: int

    def metadata(self) -> dict:
        """Safe-to-log metadata; deliberately excludes image contents."""
        return {
            "monitor_id": self.monitor_id,
            "window_title": self.window_title,
            "application": self.application,
            "width": self.width,
            "height": self.height,
            "bytes": len(self.jpeg),
        }


class VisionFrames:
    """Create bounded JPEG frames from the active game monitor."""

    def __init__(self, game_capture: GameCapture | None = None):
        self.game_capture = game_capture if game_capture is not None else GameCapture()

    def snapshot(self, fallback_monitor: int = 1, max_edge: int = 1280,
                 quality: int = 75) -> VisionFrame:
        if not 320 <= max_edge <= 3840:
            raise ValueError("max_edge must be between 320 and 3840")
        if not 30 <= quality <= 90:
            raise ValueError("quality must be between 30 and 90")

        target, original_jpeg = self.game_capture.snapshot(fallback_monitor)
        if not original_jpeg:
            raise ValueError("Screen capture returned an empty frame")

        try:
            with Image.open(BytesIO(original_jpeg)) as source:
                if source.format != "JPEG":
                    raise ValueError("Screen capture must provide JPEG bytes")
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
                width, height = image.size
                output = BytesIO()
                image.save(output, format="JPEG", quality=quality, optimize=True)
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Could not decode captured JPEG") from exc

        return VisionFrame(
            jpeg=output.getvalue(), monitor_id=target.monitor_id,
            window_title=target.window_title, application=target.application,
            width=width, height=height,
        )
