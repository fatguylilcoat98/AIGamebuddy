"""Save 1920x1080 overlay frames, and on Windows grab the real window too.

The composited frame is one LANCZOS scale from the source art to 1920x1080.
It is not a 1280 picture stretched up afterwards.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from .overlay_view import compose_overlay


def write_previews(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for frame_id in ("genesis", "nes", "snes"):
        for character in ("male", "female"):
            image = compose_overlay(
                frame_id, (1920, 1080), expression="idle", character=character, resting="left",
            ).convert("RGB")
            path = directory / f"overlay-1920-{frame_id}-{character}.jpg"
            image.save(path, quality=90)
            written.append(path)
        talk = compose_overlay(
            frame_id, (1920, 1080), expression="talk", mouth=0.8, character="male", resting="left",
        ).convert("RGB")
        talk_path = directory / f"overlay-1920-{frame_id}-talk.jpg"
        talk.save(talk_path, quality=90)
        written.append(talk_path)
    return written


def grab_window(directory: Path) -> Path | None:
    """Open the composited Genesis frame in a real window and screenshot it."""
    if sys.platform != "win32":
        return None
    try:
        import tkinter as tk
        from PIL import ImageGrab, ImageTk
    except Exception as exc:
        print(f"window grab skipped: {exc}")
        return None
    image = compose_overlay("genesis", (1280, 720), expression="idle", character="male", resting="left")
    root = tk.Tk()
    root.title("Buddy preview")
    root.geometry("1280x720+40+40")
    photo = ImageTk.PhotoImage(image.convert("RGB"))
    label = tk.Label(root, image=photo, bd=0)
    label.pack()
    root.update()
    root.after(800, root.update)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    try:
        shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    except Exception as exc:
        print(f"window grab skipped: {exc}")
        root.destroy()
        return None
    path = directory / "windows-genesis-window.jpg"
    shot.save(path, quality=90)
    root.destroy()
    return path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    directory = Path(args[0]) if args else Path("assets/previews")
    for path in write_previews(directory):
        print(path)
    grabbed = grab_window(directory)
    if grabbed:
        print(grabbed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
