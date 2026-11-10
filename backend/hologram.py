"""Buddy's hologram, drawn from Chris's GB-cap sprite sheets.

Yaw is -1 (strong left, toward the game) through 0 (camera) to +1 (strong right).
The default rest is a left profile toward the game window. It stays there while
idle. Only talking turns the head to face the viewer. Turns cross-fade between
sheets and add a little squash, skew, and pedestal parallax.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .hologram_art import TURN_EXPRESSIONS, get_art

EXPRESSIONS = (
    "idle", "blink", "talk", "smile", "wink", "laugh",
    "smug", "shocked", "celebrate", "sad",
)

_FRONT = {
    "idle": "neutral",
    "blink": "neutral",
    "talk": "talk",
    "smile": "grin",
    "wink": "wink",
    "laugh": "laugh",
    "smug": "smug",
    "shocked": "shocked",
    "celebrate": "grin",
    "sad": "sad",
}


def normalize_character(value: str | None) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"male", "m", "man"}:
        return "male"
    if text in {"female", "f", "woman"}:
        return "female"
    return None


def normalize_resting(value: str | None) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"left", "l", "game"}:
        return "left"
    if text in {"right", "r"}:
        return "right"
    if text in {"center", "centre", "camera", "forward"}:
        return "center"
    return None


def yaw_at(t: float, expression: str, resting: str = "left", gaze: str = "center") -> float:
    """Rest stays in profile. Only talking turns the head toward the viewer."""
    if expression == "talk":
        return 0.0
    drift = 0.05 * math.sin(t * 0.65)
    if resting == "right":
        return min(1.0, 0.9 + drift)
    if resting == "center":
        return drift
    # Left rest is a three-quarter/side profile toward the game, not a front view.
    return max(-1.0, min(-0.82, -0.92 + drift))


def _smooth(value: float) -> float:
    return value * value * (3 - 2 * value)


def _blend_pair(frames: list[tuple[float, Image.Image]], magnitude: float) -> Image.Image:
    if magnitude <= frames[0][0]:
        return frames[0][1]
    if magnitude >= frames[-1][0]:
        return frames[-1][1]
    for index in range(len(frames) - 1):
        start, end = frames[index][0], frames[index + 1][0]
        if start <= magnitude <= end:
            span = end - start
            mix = 0.0 if span <= 0 else _smooth((magnitude - start) / span)
            return Image.blend(frames[index][1], frames[index + 1][1], mix)
    return frames[-1][1]


def _pose_sprite(character: str, expression: str, yaw: float, mouth: float) -> Image.Image:
    art = get_art(character)
    magnitude = abs(yaw)
    side_turns = art.left_turns if yaw < 0 else art.right_turns
    side_expr = art.left_expr if yaw < 0 else art.right_expr
    base = _blend_pair(side_turns, magnitude)
    name = _FRONT.get(expression, "neutral")
    if expression != "talk" and yaw <= -0.75 and art.rest_left is not None:
        if expression in {"laugh", "shocked", "celebrate"} and name in side_expr:
            return side_expr[name]
        return art.rest_left
    if expression == "talk":
        opened = art.front["talk"]
        closed = art.front["neutral"]
        level = max(0.0, min(1.0, (mouth - 0.12) / 0.55))
        return Image.blend(closed, opened, level)
    if name in TURN_EXPRESSIONS and magnitude > 0.38 and name in side_expr:
        turned = side_expr[name]
        return Image.blend(base, turned, 0.82)
    if name == "neutral":
        return base
    front = art.front.get(name, art.front["neutral"])
    if magnitude < 0.28:
        return front
    return Image.blend(base, front, 0.55)


def _squash_skew(image: Image.Image, yaw: float) -> Image.Image:
    width, height = image.size
    squeeze = 1 - 0.12 * math.sin(min(1.0, abs(yaw)) * math.pi)
    squeeze = max(0.82, squeeze)
    shear = -0.07 * yaw
    inverse_x = 1 / squeeze
    center_x = width / 2
    center_y = height / 2
    # dst (x, y) samples src (a x + b y + c, y)
    slope = shear * (width / max(1, height))
    coefficients = (
        inverse_x,
        -slope,
        center_x - inverse_x * center_x + slope * center_y,
        0,
        1,
        0,
    )
    return image.transform(image.size, Image.Transform.AFFINE, coefficients, resample=Image.Resampling.BICUBIC)


def _shift(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    out = np.zeros_like(image)
    height, width = image.shape[:2]
    src_x0 = max(0, -dx)
    src_y0 = max(0, -dy)
    dst_x0 = max(0, dx)
    dst_y0 = max(0, dy)
    copy_w = min(width - src_x0, width - dst_x0)
    copy_h = min(height - src_y0, height - dst_y0)
    if copy_w > 0 and copy_h > 0:
        out[dst_y0:dst_y0 + copy_h, dst_x0:dst_x0 + copy_w] = image[src_y0:src_y0 + copy_h, src_x0:src_x0 + copy_w]
    return out


def _parallax(image: Image.Image, yaw: float, t: float) -> Image.Image:
    array = np.array(image)
    alpha = array[:, :, 3]
    rows = np.where(alpha.max(axis=1) > 20)[0]
    if len(rows) < 8:
        return image
    split = int(rows[0] + (rows[-1] - rows[0]) * 0.8)
    head = array.copy()
    head[split:] = 0
    pedestal = array.copy()
    pedestal[:split] = 0
    width = array.shape[1]
    head_dx = int(round(-yaw * width * 0.035))
    pedestal_dx = int(round(yaw * width * 0.018))
    float_dy = int(round(math.sin(t * 1.25) * array.shape[0] * 0.012))
    combined = _shift(pedestal, pedestal_dx, 0)
    moved = _shift(head, head_dx, float_dy)
    # Porter-Duff source-over of the head onto the pedestal.
    src_a = moved[:, :, 3:4].astype(np.float32) / 255.0
    dst_a = combined[:, :, 3:4].astype(np.float32) / 255.0
    out_a = src_a + dst_a * (1 - src_a)
    out_rgb = moved[:, :, :3].astype(np.float32) * src_a + combined[:, :, :3].astype(np.float32) * dst_a * (1 - src_a)
    safe = np.clip(out_a, 1e-4, 1)
    rgb = np.clip(out_rgb / safe, 0, 255).astype(np.uint8)
    alpha_out = np.clip(out_a * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, alpha_out]), "RGBA")


def _blink(image: Image.Image, amount: float) -> Image.Image:
    if amount <= 0.02:
        return image
    array = np.array(image)
    alpha = array[:, :, 3]
    rows = np.where(alpha.max(axis=1) > 30)[0]
    if len(rows) < 8:
        return image
    top, bottom = int(rows[0]), int(rows[-1])
    span = bottom - top
    y0 = top + int(span * 0.38)
    y1 = top + int(span * 0.45)
    shade = array.copy()
    band = shade[y0:y1, :, :3].astype(np.float32) * (1 - 0.45 * amount)
    shade[y0:y1, :, :3] = band.astype(np.uint8)
    lid = (y0 + y1) // 2
    shade[lid:lid + 2, :, 1] = np.clip(shade[lid:lid + 2, :, 1].astype(np.int16) + int(90 * amount), 0, 255)
    shade[lid:lid + 2, :, 2] = np.clip(shade[lid:lid + 2, :, 2].astype(np.int16) + int(50 * amount), 0, 255)
    return Image.blend(image, Image.fromarray(shade, "RGBA"), max(0.0, min(1.0, amount)))


def _blink_amount(t: float, expression: str) -> float:
    if expression == "blink":
        return 1.0
    if expression not in {"idle", "smile", "smug"}:
        return 0.0
    phase = t % 4.6
    if phase < 4.42 or phase > 4.58:
        return 0.0
    return 1 - abs(phase - 4.50) / 0.08


def _scanlines(image: Image.Image, t: float, burst: float) -> Image.Image:
    """A moving shimmer. Brightness stays steady so the hologram does not flash."""
    array = np.array(image)
    breathe = 0.98 + 0.02 * math.sin(t * 1.6)
    array[:, :, :3] = np.clip(array[:, :, :3].astype(np.float32) * breathe, 0, 255).astype(np.uint8)
    phase = int(t * 10.0) % 4
    for y in range(phase, array.shape[0], 4):
        array[y, :, 3] = (array[y, :, 3].astype(np.float32) * 0.86).astype(np.uint8)
    if burst > 0:
        array[:, :, 1] = np.clip(array[:, :, 1].astype(np.int16) + int(40 * burst), 0, 255)
        array[:, :, 2] = np.clip(array[:, :, 2].astype(np.int16) + int(55 * burst), 0, 255)
    return Image.fromarray(array, "RGBA")


def _fit(sprite: Image.Image, size: int, offset: tuple[float, float], scale: float) -> Image.Image:
    target = max(8, int(size * 0.94 * scale))
    fitted = sprite.copy()
    fitted.thumbnail((target, target), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - fitted.width) // 2 + int(offset[0])
    y = (size - fitted.height) // 2 + int(offset[1])
    canvas.alpha_composite(fitted, (x, y))
    return canvas


def step_yaw(current: float, target: float, rate: float = 0.28) -> float:
    """Move the head part of the way toward `target` so the turn is smooth."""
    now = float(current) + (float(target) - float(current)) * rate
    return max(-1.0, min(1.0, now))


def _compose(expression: str, t: float, mouth: float, gaze: str, size: int,
             character: str, resting: str, yaw_override: float | None = None) -> Image.Image:
    yaw = yaw_at(t, expression, resting, gaze) if yaw_override is None else max(-1.0, min(1.0, float(yaw_override)))
    sprite = _pose_sprite(character, expression, yaw, mouth)
    # Talking turns toward the player. Idle still floats, it does not freeze.
    if expression == "talk" or abs(yaw) < 0.75:
        sprite = _squash_skew(sprite, yaw)
        sprite = _parallax(sprite, yaw, t)
    else:
        sprite = _parallax(sprite, yaw * 0.15, t)
    sprite = _blink(sprite, _blink_amount(t, expression))
    bob = math.sin(t * 1.7) * size * 0.02
    sway = math.sin(t * 0.8) * size * 0.012
    burst = 0.0
    scale = 1.0
    if expression == "celebrate":
        bob -= abs(math.sin(t * 6.0)) * size * 0.05
        scale = 1.05
        burst = 0.55 + 0.45 * abs(math.sin(t * 6.0))
    elif expression == "shocked":
        sway += math.sin(t * 28.0) * size * 0.01
    fitted = _fit(sprite, size, (sway - yaw * size * 0.02, bob), scale)
    if burst > 0:
        glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        pad = int(size * (0.08 + 0.05 * burst))
        draw.ellipse((pad, pad, size - pad, size - pad), fill=(40, 170, 255, int(70 * burst)))
        fitted = Image.alpha_composite(glow, fitted)
    # The sprite already has its pedestal ring. A second ellipse at 78% of the
    # square sat on the neck instead of under the chin.
    return _scanlines(fitted, t, burst)


def render_hologram(expression: str = "idle", t: float = 0.4, mouth: float = 0.0,
                    gaze: str = "center", size: int = 256, character: str = "male",
                    resting: str = "left", from_expression: str | None = None,
                    blend: float = 1.0, yaw: float | None = None) -> Image.Image:
    if expression not in EXPRESSIONS:
        expression = "idle"
    character = character if character in {"male", "female"} else "male"
    resting = resting if resting in {"left", "right", "center"} else "left"
    current = _compose(expression, t, mouth, gaze, size, character, resting, yaw)
    amount = max(0.0, min(1.0, float(blend)))
    if from_expression and from_expression != expression and amount < 0.999:
        previous = _compose(from_expression, t, mouth, gaze, size, character, resting, yaw)
        return Image.blend(previous, current, amount)
    return current
