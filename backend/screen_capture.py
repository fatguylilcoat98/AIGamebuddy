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
        import os
        import tempfile
        if os.name == "nt":
            return _jpeg_rect_isolated(left, top, width, height)
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


def _jpeg_rect_isolated(left: int, top: int, width: int, height: int) -> bytes:
    """mss runs in a child process so a capture crash does not kill Buddy."""
    import logging
    import subprocess
    import tempfile
    from pathlib import Path
    from .hidden_process import run as hidden_run
    from .native_guard import crashed, mark, probe, python_exe
    import os
    log = logging.getLogger("buddy.capture")
    if probe("capture", "import mss") != "ok":
        raise RuntimeError("Screen capture is off. The capture library did not load, so Buddy will not look at the screen.")
    fd, dest = tempfile.mkstemp(suffix=".jpg", prefix="buddy-cap-")
    os.close(fd)
    try:
        done = hidden_run(
            [python_exe(), "-m", "backend.capture_worker",
             str(left), str(top), str(width), str(height), dest],
            capture_output=True, text=True, timeout=12, check=False,
        )
        if crashed(done.returncode):
            mark("capture", "crashed")
            log.warning(
                "Screen capture is off. The capture library crashed (code %s), so Buddy will not look at the screen.",
                done.returncode,
            )
            raise RuntimeError("Screen capture crashed")
        if done.returncode != 0:
            detail = ((done.stderr or "") + (done.stdout or "")).strip()
            log.warning("Screen capture failed. %s", detail[-300:])
            raise RuntimeError(detail or "Screen capture failed")
        data = Path(dest).read_bytes()
        if not data:
            raise RuntimeError("Screen capture returned an empty frame")
        return data
    except subprocess.TimeoutExpired:
        mark("capture", "crashed")
        log.warning("Screen capture is off. The capture hung, so Buddy will not look at the screen.")
        raise RuntimeError("Screen capture hung")
    finally:
        try:
            os.remove(dest)
        except OSError:
            pass
