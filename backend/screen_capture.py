"""Read-only screen capture for the selected Windows monitor."""
from io import BytesIO
import mss
from PIL import Image

class ScreenCapture:
    def monitors(self):
        with mss.mss() as sct:
            return [
                {"id": i, "left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
                for i, m in enumerate(sct.monitors) if i > 0
            ]

    def jpeg(self, monitor=1):
        with mss.mss() as sct:
            if monitor < 1 or monitor >= len(sct.monitors):
                raise ValueError(f"Monitor {monitor} not found. Use /monitors to list available monitors.")
            shot = sct.grab(sct.monitors[monitor])
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        output = BytesIO()
        image.save(output, format="JPEG", quality=75, optimize=True)
        return output.getvalue()

    def close(self):
        pass
