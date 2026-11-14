"""Grab one rectangle to a JPEG file. A crash stays in this process."""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 5:
        print("usage: capture_worker.py left top width height dest.jpg")
        return 1
    try:
        left, top, width, height = (int(part) for part in args[:4])
        dest = Path(args[4])
        import mss
        from PIL import Image
        from io import BytesIO
        from backend.capture_safety import bgra_to_rgb
        with mss.mss() as sct:
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
            rgb = bgra_to_rgb(shot.raw, shot.width, shot.height)
            image = Image.frombytes("RGB", (shot.width, shot.height), rgb)
        output = BytesIO()
        image.save(output, format="JPEG", quality=75, optimize=True)
        dest.write_bytes(output.getvalue())
    except Exception as exc:
        print(f"ERROR {exc}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
