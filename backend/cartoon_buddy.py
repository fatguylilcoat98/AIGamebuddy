"""A rigged cartoon Buddy, drawn from parts every frame.

The head is not a photo tipped on its side. Eyes, brows, and the mouth are
separate shapes. Yaw eases the head toward the game or the player. The mouth
shape follows the voice level, and a blink, a breath, and a few reactions
keep him moving.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw


def _skin(character: str) -> tuple[int, int, int]:
    return (232, 186, 150) if character == "male" else (236, 196, 176)


def _shirt(character: str) -> tuple[int, int, int]:
    return (36, 110, 210) if character == "male" else (196, 64, 150)


def _hair(character: str) -> tuple[int, int, int]:
    return (42, 28, 22) if character == "male" else (92, 48, 28)


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


def render_cartoon(size: int = 240, t: float = 0.0, yaw: float = -0.9, mouth: float = 0.0,
                   expression: str = "idle", character: str = "male", talking: bool = False) -> Image.Image:
    """One frame. `yaw` -1 faces the game, 0 faces the player."""
    size = max(64, int(size))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # A cyan plate so he still reads in the black well, without being a tilted photo.
    draw.ellipse(
        (int(size * 0.18), int(size * 0.06), int(size * 0.82), int(size * 0.94)),
        fill=(40, 170, 255, 210),
    )
    character = character if character in {"male", "female"} else "male"
    yaw = max(-1.0, min(1.0, float(yaw)))
    breath = 1.0 + 0.025 * math.sin(t * 2.2)
    blink = expression == "blink" or (3.2 < (t % 3.6) < 3.42)
    if expression == "laugh":
        blink = abs(math.sin(t * 8.0)) > 0.35
    face_x = int(yaw * size * 0.07)
    face_y = int(math.sin(t * 1.7) * size * 0.012)
    if expression == "shocked":
        face_y -= int(size * 0.02)
    cx = size // 2 + face_x
    cy = int(size * 0.46) + face_y
    skin = _skin(character)
    shirt = _shirt(character)
    hair = _hair(character)

    # Body and a small breath.
    body_w = int(size * 0.34 * breath)
    body_h = int(size * 0.28)
    body_top = int(size * 0.62)
    draw.rounded_rectangle(
        (cx - body_w, body_top, cx + body_w, body_top + body_h),
        radius=size // 10, fill=shirt + (255,),
    )
    _arms(draw, size, cx, body_top, expression, shirt)

    # Neck and head.
    draw.rectangle((cx - size // 18, cy + size // 10, cx + size // 18, body_top + 4), fill=skin + (255,))
    head_r = int(size * 0.24)
    # A turn shifts the cranium so a three-quarter view is not a rotated sticker.
    head_dx = int(yaw * head_r * 0.22)
    draw.ellipse((cx - head_r + head_dx, cy - head_r, cx + head_r + head_dx, cy + head_r), fill=skin + (255,))
    if character == "female":
        draw.ellipse((cx + head_r // 2, cy - head_r // 5, cx + head_r + size // 8, cy + head_r // 2), fill=hair + (255,))
    else:
        draw.pieslice((cx - head_r + head_dx, cy - head_r, cx + head_r + head_dx, cy + head_r // 3), 200, 340, fill=hair + (255,))

    # Cap, so he still reads as Buddy.
    cap_top = cy - int(head_r * 0.95)
    draw.chord((cx - head_r + head_dx, cap_top, cx + head_r + head_dx, cy + head_r // 8), 200, 340, fill=(24, 28, 36, 255))
    brim = int(size * 0.08 * (1 - 0.35 * abs(yaw)))
    draw.polygon([
        (cx - head_r // 2 + head_dx, cy - head_r // 5),
        (cx + head_r // 2 + head_dx + int(yaw * 8), cy - head_r // 5),
        (cx + brim, cy - head_r // 10),
    ], fill=(24, 28, 36, 255))

    _brows(draw, size, cx + head_dx, cy, expression, yaw)
    _eyes(draw, size, cx + head_dx, cy, yaw, blink, expression)
    _mouth(draw, size, cx + int(yaw * head_r * 0.18) + head_dx, cy + head_r // 3, viseme(mouth, t, talking or expression == "talk"), expression)
    if expression == "sad":
        # Facepalm. The hand is a part, not a tilt of the whole body.
        hand = int(size * 0.07)
        hx = cx + int(head_r * 0.45)
        hy = cy + head_r // 6
        draw.ellipse((hx - hand, hy - hand, hx + hand, hy + hand), fill=skin + (255,))
    return canvas


def render_booth(size: int, t: float, yaw: float, mouth: float, expression: str,
                 talking_as: str, announcer_mouth: float = 0.0) -> Image.Image:
    """Guy and girl Buddy side by side. Only the one talking moves their mouth."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    half = max(48, size // 2)
    male_mouth = mouth if talking_as == "male" else 0.0
    female_mouth = announcer_mouth if talking_as == "female" else (mouth if talking_as == "female" else 0.0)
    if talking_as != "female":
        female_mouth = 0.0
    if talking_as != "male":
        male_mouth = 0.0
    male = render_cartoon(half, t, yaw, male_mouth, expression if talking_as == "male" else "idle", "male", talking_as == "male")
    female = render_cartoon(half, t + 0.4, yaw * 0.6, female_mouth, expression if talking_as == "female" else "idle", "female", talking_as == "female")
    canvas.alpha_composite(male, (0, size - half))
    canvas.alpha_composite(female, (size - half, size - half))
    return canvas


def _arms(draw: ImageDraw.ImageDraw, size: int, cx: int, body_top: int, expression: str, shirt: tuple[int, int, int]) -> None:
    arm_w = max(6, size // 16)
    if expression == "celebrate":
        draw.rounded_rectangle((cx - size // 3, body_top - size // 5, cx - size // 3 + arm_w, body_top + 4), radius=4, fill=shirt + (255,))
        draw.rounded_rectangle((cx + size // 3 - arm_w, body_top - size // 5, cx + size // 3, body_top + 4), radius=4, fill=shirt + (255,))
        return
    draw.rounded_rectangle((cx - size // 4 - arm_w, body_top + 4, cx - size // 4, body_top + size // 5), radius=4, fill=shirt + (255,))
    draw.rounded_rectangle((cx + size // 4, body_top + 4, cx + size // 4 + arm_w, body_top + size // 5), radius=4, fill=shirt + (255,))


def _brows(draw: ImageDraw.ImageDraw, size: int, cx: int, cy: int, expression: str, yaw: float) -> None:
    y = cy - size // 14
    span = int(size * 0.16)
    shift = int(yaw * size * 0.03)
    lift = 0
    if expression in {"shocked", "laugh"}:
        lift = -size // 28
    if expression == "sad":
        lift = size // 40
    color = (48, 32, 24, 255)
    draw.arc((cx - span + shift, y + lift, cx - 2 + shift, y + size // 16 + lift), 200, 340, fill=color, width=max(2, size // 40))
    draw.arc((cx + 2 + shift, y + lift, cx + span + shift, y + size // 16 + lift), 200, 340, fill=color, width=max(2, size // 40))


def _eyes(draw: ImageDraw.ImageDraw, size: int, cx: int, cy: int, yaw: float, blink: bool, expression: str) -> None:
    eye_w = max(6, size // 14)
    eye_h = max(4, size // 18)
    if expression == "shocked":
        eye_w = int(eye_w * 1.35)
        eye_h = int(eye_h * 1.45)
    y = cy - size // 28
    gap = int(size * 0.06)
    shift = int(yaw * size * 0.05)
    for side in (-1, 1):
        ex = cx + side * gap + shift
        if blink or expression == "laugh":
            draw.arc((ex - eye_w // 2, y, ex + eye_w // 2, y + eye_h), 20, 160, fill=(32, 24, 20, 255), width=max(2, size // 48))
            continue
        draw.ellipse((ex - eye_w // 2, y, ex + eye_w // 2, y + eye_h), fill=(248, 248, 252, 255))
        pupil = max(2, eye_w // 5)
        px = ex + int(yaw * eye_w * 0.15)
        py = y + eye_h // 2
        draw.ellipse((px - pupil, py - pupil, px + pupil, py + pupil), fill=(28, 36, 48, 255))


def _mouth(draw: ImageDraw.ImageDraw, size: int, cx: int, cy: int, shape: str, expression: str) -> None:
    w = max(8, size // 10)
    if expression == "laugh" or shape == "ah":
        draw.ellipse((cx - w, cy - w // 2, cx + w, cy + int(w * 0.9)), fill=(150, 48, 62, 255))
        draw.rectangle((cx - w + 2, cy - 1, cx + w - 2, cy + w // 5), fill=(248, 240, 236, 255))
        return
    if expression == "shocked" or shape == "oh":
        draw.ellipse((cx - w // 2, cy, cx + w // 2, cy + w), fill=(120, 40, 52, 255))
        return
    if shape == "ee":
        draw.rounded_rectangle((cx - w, cy + 2, cx + w, cy + max(4, w // 4)), radius=2, fill=(140, 50, 64, 255))
        return
    draw.arc((cx - w, cy, cx + w, cy + w // 2), 20, 160, fill=(120, 48, 56, 255), width=max(2, size // 48))
