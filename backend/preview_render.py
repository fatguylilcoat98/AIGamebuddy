"""Write preview images of the three frames and Buddy's expressions."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .frames import composite_with_head, render_frame
from .hologram import EXPRESSIONS, render_hologram

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "previews"


def _sheet() -> Image.Image:
    cell = 180
    cols = 5
    rows = 2
    sheet = Image.new("RGBA", (cols * cell, rows * cell + 28), (8, 12, 24, 255))
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(EXPRESSIONS):
        mouth = 0.7 if name in {"talk", "laugh", "shocked", "celebrate"} else 0.05
        gaze = "left" if name == "idle" else "center"
        head = render_hologram(name, t=0.8, mouth=mouth, gaze=gaze, size=150)
        x = (index % cols) * cell + 15
        y = (index // cols) * cell + 8
        sheet.alpha_composite(head, (x, y))
        draw.text((x, y + 152), name, fill=(220, 245, 255, 255))
    return sheet


def _gif(expression: str, mouth_from_audio: bool, path: Path) -> None:
    frames = []
    for step in range(16):
        t = step / 8
        mouth = (0.2 + 0.7 * abs(__import__("math").sin(t * 8))) if mouth_from_audio else 0.0
        frame = render_hologram(expression, t=t, mouth=mouth, size=160)
        plate = Image.new("RGBA", (160, 160), (4, 10, 24, 255))
        plate.alpha_composite(frame)
        frames.append(plate.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=80, loop=0, disposal=2)


def _on_checker(image: Image.Image) -> Image.Image:
    plate = Image.new("RGBA", image.size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(plate)
    for y in range(0, image.height, 24):
        for x in range(0, image.width, 24):
            if (x // 24 + y // 24) % 2 == 0:
                draw.rectangle((x, y, x + 23, y + 23), fill=(210, 210, 210, 255))
            else:
                draw.rectangle((x, y, x + 23, y + 23), fill=(150, 150, 150, 255))
    plate.alpha_composite(image)
    return plate


def render_all(folder: Path | None = None) -> list[Path]:
    out = folder or OUT
    out.mkdir(parents=True, exist_ok=True)
    written = []
    head = render_hologram("smile", t=0.6, mouth=0.1, size=348)
    for theme in ("nes", "snes", "genesis"):
        art = render_frame(theme, "GAME WINGMAN")
        frame_path = out / f"frame-{theme}.png"
        art.image.save(frame_path)
        checker = out / f"frame-{theme}-opening.png"
        _on_checker(art.image).save(checker)
        composite = composite_with_head(art, head)
        comp_path = out / f"frame-{theme}-with-buddy.png"
        composite.save(comp_path)
        written.extend((frame_path, checker, comp_path))
    sheet = _sheet()
    sheet_path = out / "buddy-expressions.png"
    sheet.save(sheet_path)
    written.append(sheet_path)
    idle = out / "buddy-idle.gif"
    talk = out / "buddy-talk.gif"
    _gif("idle", False, idle)
    _gif("talk", True, talk)
    written.extend((idle, talk))
    return written


if __name__ == "__main__":
    for path in render_all():
        print(path)
