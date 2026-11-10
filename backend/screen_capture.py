"""Read-only capture of a rectangle. Never the full desktop for Buddy's vision.

Screenshots are JPEG bytes for the vision API. The overlay must not draw them.
mss returns BGRA; this module converts that to RGB before encoding.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from .capture_safety import bgra_to_rgb, overlay_may_show_capture


class ScreenCapture:
    def monitors(self):
        import mss
        with mss.mss() as sct:
            return [
                {"id": i, "left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
                for i, m in enumerate(sct.monitors) if i > 0
            ]

    def jpeg_rect(self, rect: tuple[int, int, int, int]) -> bytes:
        """JPEG of one window rectangle, RGB channel order, not for the overlay."""
        if overlay_may_show_capture():
            raise RuntimeError("Captured frames must not be drawn on the overlay")
        left, top, width, height = (int(v) for v in rect)
        if width < 2 or height < 2:
            raise ValueError("Capture rectangle is too small")
        import mss
        with mss.mss() as sct:
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
            # shot.raw is BGRA. shot.rgb exists, but using raw keeps the swap explicit.
            rgb = bgra_to_rgb(shot.raw, shot.width, shot.height)
            image = Image.frombytes("RGB", (shot.width, shot.height), rgb)
        output = BytesIO()
        image.save(output, format="JPEG", quality=75, optimize=True)
        return output.getvalue()

    def close(self):
        pass
