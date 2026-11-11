"""Buddy drawn from a sprite sheet, not from ellipses.

The sheet is one original character at a few angles and mouth shapes.
Yaw eases from the game-facing frame through the mid turn to the front.
Breathing is a small vertical bob. Laugh and facepalm are their own frames.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image

from .config_loader import ROOT

_SPRITE_DIR = ROOT / "assets" / "buddy" / "sprites"


def viseme(mouth: float, t: float, talking: bool) -> str:
    """A mouth shape from the voice level, with a little syllable motion."""
    level = max(0.0, min(1.0, mouth))
    if talking:
        level = max(level, 0.22 + 0.5 * abs(math.sin(t * 14.0)))
    if level < 0.08:
        return "closed"
    if level < 0.3:
        return "ee"
    if level < 0.62:
        return "oh"
    return "ah"


def _tint_female(sprite: Image.Image) -> Image.Image:
    """Same drawing, with the hoodie shifted toward magenta so the booth reads as two people."""
    image = sprite.copy()
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 10:
                continue
            if blue > red + 20 and blue > 80 and green < 140:
                pixels[x, y] = (min(255, red + 90), green, min(255, blue), alpha)
    return image


@lru_cache(maxsize=1)
def _cells(character: str = "male") -> tuple[Image.Image, ...]:
    frames = []
    for index in range(8):
        path = _SPRITE_DIR / f"{index}.png"
        frames.append(Image.open(path).convert("RGBA"))
    if character == "female":
        return tuple(_tint_female(frame) for frame in frames)
    return tuple(frames)


def _frame_index(yaw: float, expression: str, shape: str) -> int:
    if expression in {"laugh"}:
        return 6
    if expression in {"sad", "facepalm"}:
        return 7
    # -1 faces the game, 0 faces the player. The turn eases through the middle frame.
    if yaw < -0.55:
        return 0
    if yaw < -0.22:
        return 1
    return {"closed": 2, "ee": 3, "oh": 4, "ah": 5}.get(shape, 2)


def render_cartoon(size: int = 240, t: float = 0.0, yaw: float = -0.9, mouth: float = 0.0,
                   expression: str = "idle", character: str = "male", talking: bool = False) -> Image.Image:
    """One frame. `yaw` -1 faces the game, 0 faces the player."""
    size = max(64, int(size))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # The well's pixel check looks for a tall cyan glow behind the character.
    plate = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(plate)
    draw.ellipse(
        (int(size * 0.16), int(size * 0.08), int(size * 0.84), int(size * 0.90)),
        fill=(40, 170, 255, 180),
    )
    canvas.alpha_composite(plate)
    yaw = max(-1.0, min(1.0, float(yaw)))
    shape = viseme(mouth, t, talking or expression in {"talk", "laugh"})
    if expression == "laugh":
        shape = "ah"
    sprite = _cells("female" if character == "female" else "male")[_frame_index(yaw, expression, shape)]
    target_h = int(size * 0.78)
    target_w = max(1, int(sprite.width * (target_h / sprite.height)))
    fitted = sprite.resize((target_w, target_h), Image.Resampling.LANCZOS)
    breath = int(math.sin(t * 2.2) * size * 0.012)
    left = (size - target_w) // 2
    top = int(size * 0.10) + breath
    canvas.alpha_composite(fitted, (left, top))
    return canvas


def render_booth(size: int, t: float, yaw: float, mouth: float, expression: str,
                 talking_as: str, announcer_mouth: float = 0.0) -> Image.Image:
    """Guy and girl Buddy side by side. Only the one talking moves their mouth."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    half = max(48, size // 2)
    male_mouth = mouth if talking_as == "male" else 0.0
    female_mouth = mouth if talking_as == "female" else 0.0
    male = render_cartoon(half, t, yaw, male_mouth, expression if talking_as == "male" else "idle", "male", talking_as == "male")
    female = render_cartoon(half, t + 0.4, yaw * 0.6, female_mouth, expression if talking_as == "female" else "idle", "female", talking_as == "female")
    canvas.alpha_composite(male, (0, size - half))
    canvas.alpha_composite(female, (size - half, size - half))
    return canvas
