"""Save 1920x1080 overlay frames, and on Windows grab the real window too.

The composited frame is one LANCZOS scale from the source art to 1920x1080.
It is not a 1280 picture stretched up afterwards.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .overlay_view import compose_overlay, layout_boxes

_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _test_pattern(image: Image.Image) -> Image.Image:
    """Fill the transparent opening with a picture so a review can see the game hole."""
    import numpy as np
    array = np.array(image.convert("RGBA"))
    hole = array[:, :, 3] < 16
    height, width = hole.shape
    ys, xs = np.indices((height, width))
    colors = np.array([
        [220, 170, 40], [40, 190, 210], [40, 190, 70], [190, 50, 190],
        [200, 50, 50], [50, 70, 200], [230, 120, 40], [30, 30, 30],
    ], dtype=np.uint8)
    picture = colors[(xs * 8 // max(1, width)) % 8]
    grid = ((xs % 48) < 2) | ((ys % 48) < 2)
    picture[grid] = 245
    array[hole, :3] = picture[hole]
    array[hole, 3] = 255
    return Image.fromarray(array, "RGBA")


def _draw_menu(image: Image.Image, frame_id: str) -> Image.Image:
    """The buttons Buddy shows beside the portrait when the menu is open."""
    canvas = image.convert("RGBA")
    menu = layout_boxes(frame_id, canvas.size, game_running=True)["menu"]
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (menu["x"], menu["y"], menu["x"] + menu["width"], menu["y"] + menu["height"]),
        radius=10, fill=(18, 18, 26, 235),
    )
    rows = (("Buddy: Male",), ("Sassy", "Voice", "Rest"), ("Sound", "Games", "Full"))
    size = max(20, min(28, menu["height"] // 6))
    try:
        font = ImageFont.truetype(_FONT, size)
    except OSError:
        font = ImageFont.load_default()
    row_h = menu["height"] // len(rows)
    for row_index, labels in enumerate(rows):
        widths = []
        for label in labels:
            box = draw.textbbox((0, 0), label, font=font)
            widths.append(box[2] - box[0])
        gap = 14
        total = sum(widths) + gap * (len(labels) - 1)
        x = menu["x"] + max(8, (menu["width"] - total) // 2)
        y = menu["y"] + row_index * row_h + max(2, (row_h - size) // 2)
        for label, width in zip(labels, widths):
            draw.text((x, y), label, font=font, fill=(232, 244, 255, 255))
            x += width + gap
    return canvas


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
        playing = _test_pattern(compose_overlay(
            frame_id, (1920, 1080), expression="idle", character="male", resting="left",
            game_running=True,
        ))
        game_path = directory / f"windows-1920-game-{frame_id}.jpg"
        playing.convert("RGB").save(game_path, quality=90)
        written.append(game_path)
    menu_shot = _draw_menu(_test_pattern(compose_overlay(
        "genesis", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )), "genesis")
    menu_path = directory / "windows-1920-menu-genesis.jpg"
    menu_shot.convert("RGB").save(menu_path, quality=90)
    written.append(menu_path)
    for index, (tick, expression, mouth) in enumerate((
        (0.15, "idle", 0.0),
        (0.7, "idle", 0.0),
        (1.4, "talk", 0.85),
        (2.2, "smile", 0.0),
    )):
        frame = _test_pattern(compose_overlay(
            "snes", (1920, 1080), expression=expression, mouth=mouth, t=tick,
            character="male", resting="left", game_running=True,
        ))
        path = directory / f"windows-1920-anim-{index}.jpg"
        frame.convert("RGB").save(path, quality=90)
        written.append(path)
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
    image = _test_pattern(compose_overlay(
        "genesis", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    ))
    root = tk.Tk()
    root.title("Buddy preview")
    root.geometry("1920x1080+0+0")
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
    directory.mkdir(parents=True, exist_ok=True)
    from .config_loader import ROOT as root
    strip = root / "assets" / "previews" / "buddy-frame-strip.png"
    if strip.exists() and directory.resolve() != strip.parent.resolve():
        target = directory / "buddy-frame-strip.png"
        target.write_bytes(strip.read_bytes())
        print(target)
    for path in write_previews(directory):
        print(path)
    grabbed = grab_window(directory)
    if grabbed:
        print(grabbed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
