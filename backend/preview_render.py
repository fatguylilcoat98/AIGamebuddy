"""Write preview images of the three frames and Buddy's hologram."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .frame_library import FRAME_DIR, FRAME_FILES, PLACEMENTS, paste_head
from .frames import composite_with_head, render_frame
from .hologram import EXPRESSIONS, render_hologram

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "previews"


def _sheet(character: str) -> Image.Image:
    cell = 180
    cols = 5
    rows = 2
    sheet = Image.new("RGBA", (cols * cell, rows * cell + 28), (0, 0, 0, 255))
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(EXPRESSIONS):
        mouth = 0.85 if name in {"talk", "laugh", "shocked", "celebrate"} else 0.0
        head = render_hologram(name, t=0.4, mouth=mouth, size=160, character=character, resting="center")
        x = (index % cols) * cell + 10
        y = (index // cols) * cell + 4
        sheet.alpha_composite(head, (x, y))
        draw.text((x, y + 158), name, fill=(210, 240, 255, 255))
    return sheet


def _gif(path: Path, *, character: str, expression: str, mouth: bool, turn: bool) -> None:
    frames = []
    steps = 20
    period = (2 * math.pi / 0.55) if turn else 2.4
    for step in range(steps):
        t = step / steps * period
        level = (0.15 + 0.8 * abs(math.sin(t * 8))) if mouth else 0.0
        frame = render_hologram(
            expression, t=t, mouth=level, size=200, character=character,
            resting="left" if turn or expression == "idle" else "center",
        )
        plate = Image.new("RGBA", (200, 200), (0, 0, 0, 255))
        plate.alpha_composite(frame)
        frames.append(plate.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=90, loop=0, disposal=2)


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


def render_approved(folder: Path | None = None) -> list[Path]:
    """Rest pose (left profile) and talking pose (toward the viewer) on each frame."""
    out = folder or OUT
    out.mkdir(parents=True, exist_ok=True)
    written = []
    rest = render_hologram("idle", t=0.4, mouth=0.0, size=360, character="male", resting="left")
    talking = render_hologram("talk", t=0.4, mouth=0.85, size=360, character="male", resting="left")
    for frame_id, filename in FRAME_FILES.items():
        source = Image.open(FRAME_DIR / filename).convert("RGBA")
        box = PLACEMENTS[frame_id]["buddy"]
        rest_path = out / f"approved-{frame_id}.jpg"
        talk_path = out / f"approved-{frame_id}-talking.jpg"
        paste_head(source, rest, box).convert("RGB").save(rest_path, quality=92)
        paste_head(source, talking, box).convert("RGB").save(talk_path, quality=92)
        written.extend((rest_path, talk_path))
    return written


def render_all(folder: Path | None = None) -> list[Path]:
    out = folder or OUT
    out.mkdir(parents=True, exist_ok=True)
    written = []
    head = render_hologram("smile", t=0.6, mouth=0.2, size=348, character="male", resting="left")
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
    for character in ("male", "female"):
        sheet = _sheet(character)
        sheet_path = out / f"buddy-expressions-{character}.png"
        sheet.save(sheet_path)
        written.append(sheet_path)
        idle = out / f"buddy-idle-{character}.gif"
        talk = out / f"buddy-talk-{character}.gif"
        turn = out / f"buddy-turn-{character}.gif"
        _gif(idle, character=character, expression="idle", mouth=False, turn=True)
        _gif(talk, character=character, expression="talk", mouth=True, turn=False)
        _gif(turn, character=character, expression="idle", mouth=False, turn=True)
        written.extend((idle, talk, turn))
    shutil.copyfile(out / "buddy-expressions-male.png", out / "buddy-expressions.png")
    shutil.copyfile(out / "buddy-idle-male.gif", out / "buddy-idle.gif")
    shutil.copyfile(out / "buddy-talk-male.gif", out / "buddy-talk.gif")
    written.extend((out / "buddy-expressions.png", out / "buddy-idle.gif", out / "buddy-talk.gif"))
    return written


if __name__ == "__main__":
    for path in render_approved():
        print(path)
    for path in render_all():
        print(path)
