"""Original cartoon hologram of Buddy.

This is a new character: a rounded headset face with a glass visor.
It is not a photograph and it is not named Zion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter

EXPRESSIONS = (
    "idle", "blink", "talk", "smile", "wink", "laugh",
    "smug", "shocked", "celebrate", "sad",
)


@dataclass
class Pose:
    expression: str
    gaze_x: float
    gaze_y: float
    blink: float
    wink: float
    mouth: float
    smile: float
    squint: float
    brow: float
    bob: float
    shake: float
    sparkle: float
    lid: float


def pose_for(expression: str, t: float, mouth: float = 0.0, gaze: str = "center") -> Pose:
    if expression not in EXPRESSIONS:
        expression = "idle"
    gaze_x = {"left": -0.85, "right": 0.85}.get(gaze, 0.0)
    gaze_y = {"up": -0.45, "down": 0.55}.get(gaze, 0.0)
    blink = 1.0 if (t % 4.6) > 4.38 else 0.0
    bob = math.sin(t * 1.6) * 3.0
    look = math.sin(t * 0.55)
    if expression == "idle":
        gaze_x = look * 0.75 if gaze == "center" else gaze_x
        gaze_y = math.sin(t * 0.33) * 0.25 if gaze == "center" else gaze_y
        return Pose(expression, gaze_x, gaze_y, blink, 0, mouth, 0.35, 0, 0, bob, 0, 0, 0.15)
    if expression == "blink":
        return Pose(expression, gaze_x, gaze_y, 1, 0, mouth, 0.2, 0, 0, bob * 0.4, 0, 0, 0.1)
    if expression == "talk":
        openness = mouth if mouth > 0 else (0.35 + 0.45 * abs(math.sin(t * 14)))
        return Pose(expression, gaze_x * 0.4, gaze_y, blink * 0.3, 0, openness, 0.15, 0, 0.05, bob, 0, 0, 0.1)
    if expression == "smile":
        return Pose(expression, gaze_x, gaze_y, blink, 0, max(mouth, 0.08), 0.9, 0.05, 0.1, bob, 0, 0.2, 0.05)
    if expression == "wink":
        return Pose(expression, 0.2, gaze_y, 0, 1, max(mouth, 0.05), 0.75, 0, 0.3, bob, 0, 0.15, 0.2)
    if expression == "laugh":
        return Pose(expression, gaze_x * 0.2, -0.1, 0, 0, max(mouth, 0.9), 0.8, 0.65, 0.2,
                    math.sin(t * 10) * 4, 0, 0.4, 0)
    if expression == "smug":
        return Pose(expression, 0.55, 0.2, 0, 0, 0.02, 0.35, 0.45, 0.9, bob * 0.3, 0, 0, 0.55)
    if expression == "shocked":
        jitter = math.sin(t * 28) * 2.5
        return Pose(expression, 0, -0.35, 0, 0, 0.45, 0, 0, -0.8, 0, jitter, 0, 0)
    if expression == "celebrate":
        return Pose(expression, 0, -0.2, 0, 0, 0.15, 1, 0.72, 0.4,
                    abs(math.sin(t * 6)) * 7, 0, 1, 0)
    # sad
    return Pose("sad", 0, 0.65, blink, 0, max(mouth, 0.04), -0.7, 0.1, -0.35, bob * 0.3, 0, 0, 0.35)


def _eye(draw: ImageDraw.ImageDraw, cx: float, cy: float, open_amount: float, gaze_x: float,
         gaze_y: float, squint: float, wide: float = 1.0) -> None:
    height = max(2.0, 26 * wide * open_amount * (1 - 0.75 * squint))
    if height <= 3.5:
        draw.line((cx - 16, cy, cx + 16, cy), fill=(220, 255, 255, 255), width=3)
        return
    box = (cx - 18, cy - height, cx + 18, cy + height)
    draw.ellipse(box, fill=(232, 255, 255, 245))
    px = cx + gaze_x * 7
    py = cy + gaze_y * min(6, height * 0.45)
    draw.ellipse((px - 7, py - 8, px + 7, py + 8), fill=(8, 24, 48, 255))
    draw.ellipse((px - 3, py - 5, px + 1, py - 1), fill=(255, 255, 255, 230))


def render_hologram(expression: str = "idle", t: float = 0.4, mouth: float = 0.0,
                    gaze: str = "center", size: int = 256) -> Image.Image:
    pose = pose_for(expression, t, mouth, gaze)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    cx = size / 2 + pose.shake
    cy = size / 2 + 8 + pose.bob
    g.ellipse((cx - 92, cy - 100, cx + 92, cy + 96), fill=(40, 190, 255, 70))
    g.ellipse((cx - 70, cy - 78, cx + 70, cy + 74), fill=(80, 230, 255, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image)

    # Headset cups. Original shapes, not a copy of a real product.
    for side in (-1, 1):
        ex = cx + side * 78
        draw.rounded_rectangle((ex - 16, cy - 28, ex + 16, cy + 36), radius=10,
                               fill=(120, 235, 255, 210), outline=(230, 255, 255, 255))
        draw.arc((cx - 78, cy - 70, cx + 78, cy + 10), 200 if side < 0 else 340, 340 if side < 0 else 20,
                 fill=(180, 250, 255, 180), width=4)

    draw.ellipse((cx - 62, cy - 74, cx + 62, cy + 70), fill=(150, 245, 255, 235),
                 outline=(240, 255, 255, 255), width=3)
    draw.ellipse((cx - 50, cy - 60, cx + 50, cy + 56), fill=(8, 32, 64, 230))
    # Forehead spark. A plain four-point mark, not a logo.
    draw.polygon([(cx, cy - 50), (cx + 5, cy - 42), (cx, cy - 34), (cx - 5, cy - 42)],
                 fill=(190, 255, 255, 220))

    eye_y = cy - 8
    left_open = 0 if pose.wink else (0 if pose.blink > 0.8 else 1)
    right_open = 0 if pose.blink > 0.8 else 1
    wide = 1.35 if pose.expression == "shocked" else 1.0
    _eye(draw, cx - 22, eye_y, left_open, pose.gaze_x, pose.gaze_y, pose.squint, wide)
    _eye(draw, cx + 22, eye_y, right_open, pose.gaze_x, pose.gaze_y, pose.squint, wide)

    # Brows.
    for side, lift in ((-1, pose.brow), (1, -pose.brow * 0.3)):
        y = eye_y - 24 - lift * 10
        draw.arc((cx + side * 22 - 16, y - 8, cx + side * 22 + 16, y + 10),
                 200, 340, fill=(190, 255, 255, 230), width=3)

    mouth_y = cy + 24
    smile = pose.smile
    if pose.expression == "shocked":
        draw.ellipse((cx - 10, mouth_y, cx + 10, mouth_y + 18), fill=(4, 16, 36, 255))
    elif pose.expression == "celebrate":
        draw.arc((cx - 22, mouth_y - 8, cx + 22, mouth_y + 18), 15, 165, fill=(255, 255, 255, 255), width=4)
    elif pose.mouth > 0.2 and pose.expression != "smug":
        open_h = 6 + pose.mouth * 22
        draw.ellipse((cx - 16, mouth_y - 2, cx + 16, mouth_y + open_h), fill=(4, 16, 36, 255))
        if pose.expression == "laugh":
            draw.rectangle((cx - 12, mouth_y + 2, cx + 12, mouth_y + 8), fill=(255, 255, 255, 230))
    else:
        start, end = (20, 160) if smile >= 0 else (200, 340)
        bend = 10 + abs(smile) * 8
        draw.arc((cx - 18, mouth_y - bend, cx + 18, mouth_y + bend), start, end,
                 fill=(210, 255, 255, 255), width=3)

    if pose.sparkle > 0:
        for index, (dx, dy) in enumerate(((-40, -78), (48, -70), (36, 68), (-46, 60))):
            if (index + int(t * 4)) % 2 and pose.sparkle < 0.9:
                continue
            sx, sy = cx + dx, cy + dy
            draw.line((sx - 4, sy, sx + 4, sy), fill=(230, 255, 255, 200), width=2)
            draw.line((sx, sy - 4, sx, sy + 4), fill=(230, 255, 255, 200), width=2)

    # Scanlines and a moving sheen so the head reads as a hologram.
    shade = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(0, size, 4):
        sd.line((0, y, size, y), fill=(0, 20, 40, 38))
    sheen_x = int((math.sin(t * 1.3) * 0.5 + 0.5) * size)
    sd.rectangle((sheen_x, 0, sheen_x + 10, size), fill=(255, 255, 255, 28))
    image.alpha_composite(shade)
    return image
