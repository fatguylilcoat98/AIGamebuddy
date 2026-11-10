"""Slice Chris's official Buddy sheets into transparent hologram sprites.

Expression sheets are the front-facing set (neutral, talk, grin, wink, laugh,
smug, shocked, sad). Turn sheets are a 4x2 grid: the top row runs from the
camera toward a strong turn, and the bottom row is three-quarter talk, grin,
shocked, and laugh.

Each panel is measured. The male turn sheet faces screen-left, so that side
keeps the original pixels and the cap text stays untouched. The female turn
sheet faces screen-right, so the left-facing set is a mirror and the cap
letters are redrawn upright. A mirror is never allowed to leave "GB" reversed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "hologram" / "source"

FRONT_NAMES = ("neutral", "talk", "grin", "wink", "laugh", "smug", "shocked", "sad")
TURN_EXPRESSIONS = ("talk", "grin", "shocked", "laugh")
TURN_MAGNITUDES = (0.12, 0.42, 0.72, 1.0)

# 7x7 upright bitmaps. Used only when a mirrored cap would show reversed letters.
_GLYPH = {
    "G": (
        "0111110",
        "1100011",
        "1100000",
        "1100111",
        "1100001",
        "1100011",
        "0111110",
    ),
    "B": (
        "1111110",
        "1100011",
        "1100011",
        "1111110",
        "1100011",
        "1100011",
        "1111110",
    ),
}


@dataclass
class CharacterArt:
    character: str
    front: dict[str, Image.Image]
    left_turns: list[tuple[float, Image.Image]]
    right_turns: list[tuple[float, Image.Image]]
    left_expr: dict[str, Image.Image]
    right_expr: dict[str, Image.Image]
    rest_left: Image.Image | None = None
    notes: list[str] = field(default_factory=list)


_CACHE: dict[str, CharacterArt] = {}


def _spans(mask: np.ndarray) -> list[tuple[int, int]]:
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return []
    groups = []
    start = prev = int(idx[0])
    for value in idx[1:]:
        value = int(value)
        if value == prev + 1:
            prev = value
        else:
            groups.append((start, prev))
            start = prev = value
    groups.append((start, prev))
    return groups


def _gaps(groups: list[tuple[int, int]], limit: int) -> list[tuple[int, int]]:
    edges = [0]
    for start, end in groups:
        edges.append((start + end) // 2)
    edges.append(limit)
    edges = sorted(set(edges))
    boxes = []
    for index in range(len(edges) - 1):
        if edges[index + 1] - edges[index] > 40:
            boxes.append((edges[index], edges[index + 1]))
    return boxes


def split_sheet(path: Path) -> list[Image.Image]:
    """Return 8 panels, row-major, from a 4x2 sheet."""
    image = Image.open(path).convert("RGB")
    array = np.asarray(image)
    strength = array.max(axis=2)
    rows = _gaps(_spans(strength.mean(axis=1) < 12), array.shape[0])
    cols = _gaps(_spans(strength.mean(axis=0) < 12), array.shape[1])
    if len(rows) != 2 or len(cols) != 4:
        raise ValueError(f"{path.name} did not split into a 4x2 grid ({len(cols)}x{len(rows)})")
    panels = []
    for top, bottom in rows:
        for left, right in cols:
            panels.append(image.crop((left, top, right, bottom)))
    return panels


def nose_offset(image: Image.Image) -> float:
    """Positive means the nose sits to the right of the neck (facing screen-right)."""
    array = np.asarray(image.convert("RGB"))
    strength = array.max(axis=2)
    ys, xs = np.where(strength > 40)
    if len(xs) < 20:
        return 0.0
    top, bottom = int(ys.min()), int(ys.max())
    height = max(1, bottom - top)
    neck = (ys > bottom - 0.12 * height) & (ys < bottom - 0.02 * height)
    if not neck.any():
        neck_x = float((xs.min() + xs.max()) / 2)
    else:
        neck_x = float(xs[neck].mean())
    nose = (ys > top + 0.40 * height) & (ys < top + 0.58 * height) & (strength[ys, xs] > 80)
    if not nose.any():
        return 0.0
    return float(xs[nose].mean() - neck_x)


def key_black(image: Image.Image) -> Image.Image:
    """Turn a near-black backdrop into transparency so the blue glow can sit in the box."""
    rgb = np.asarray(image.convert("RGB"))
    strength = rgb.max(axis=2).astype(np.float32)
    alpha = np.clip((strength - 14) * (255.0 / 42.0), 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def _largest_component(mask: np.ndarray) -> np.ndarray:
    """Keep the cap letters, including G and B when they are separate blobs."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    groups = []
    ys, xs = np.where(mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if seen[y, x]:
            continue
        stack = [(y, x)]
        seen[y, x] = True
        pixels = []
        while stack:
            cy, cx = stack.pop()
            pixels.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(pixels) < 15:
            continue
        py = sum(p[0] for p in pixels) / len(pixels)
        px = sum(p[1] for p in pixels) / len(pixels)
        if py > height * 0.4 or not (width * 0.15 < px < width * 0.85):
            continue
        groups.append((px, py, pixels))
    out = np.zeros_like(mask)
    if not groups:
        return out
    groups.sort(key=lambda item: item[0])
    # Join neighboring letter blobs on the cap into one mark.
    chosen = [groups[0]]
    for item in groups[1:]:
        if abs(item[0] - chosen[-1][0]) < width * 0.22 and abs(item[1] - chosen[-1][1]) < height * 0.12:
            chosen.append(item)
        elif len(item[2]) > len(chosen[0][2]) * 1.4 and not chosen:
            chosen = [item]
    if len(chosen) == 1 and len(groups) > 1:
        # Still pull in a nearby second letter if the first pass was strict.
        for item in groups:
            if item is chosen[0]:
                continue
            if abs(item[0] - chosen[0][0]) < width * 0.28 and abs(item[1] - chosen[0][1]) < height * 0.15:
                chosen.append(item)
    for _px, _py, pixels in chosen:
        for y, x in pixels:
            out[y, x] = True
    return out


def _dilate(mask: np.ndarray, radius: int = 2) -> np.ndarray:
    ys, xs = np.where(mask)
    out = mask.copy()
    height, width = mask.shape
    for y, x in zip(ys.tolist(), xs.tolist()):
        y0, y1 = max(0, y - radius), min(height, y + radius + 1)
        x0, x1 = max(0, x - radius), min(width, x + radius + 1)
        out[y0:y1, x0:x1] = True
    return out


def _letter_mask(array: np.ndarray) -> np.ndarray:
    red = array[:, :, 0].astype(np.int16)
    green = array[:, :, 1].astype(np.int16)
    blue = array[:, :, 2].astype(np.int16)
    content = array.max(axis=2) > 30
    rows = np.where(content.any(axis=1))[0]
    if len(rows) == 0:
        return np.zeros(array.shape[:2], dtype=bool)
    cap_limit = int(rows[0] + (rows[-1] - rows[0]) * 0.34)
    yy = np.arange(array.shape[0])[:, None]
    raw = (yy < cap_limit) & (red > 140) & (green > 175) & (blue > 195) & (red + green > blue)
    return _largest_component(raw)


def _grow_letters(array: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Spread from the bright cores across the pale letter fringe, not the cap."""
    red = array[:, :, 0].astype(np.int16)
    green = array[:, :, 1].astype(np.int16)
    blue = array[:, :, 2].astype(np.int16)
    fringe = (red > 80) & (green > 110) & (blue > 150) & (green + 15 > red)
    current = seed.copy()
    for _ in range(7):
        edge = _dilate(current, 1) & ~current
        current = current | (edge & fringe)
    return current


def _paint_gb(array: np.ndarray, mask: np.ndarray) -> None:
    ys, xs = np.where(mask)
    if len(xs) < 12:
        return
    content = array.max(axis=2) > 30
    rows = np.where(content.any(axis=1))[0]
    if len(rows) == 0:
        return
    head_h = max(1, int(rows[-1] - rows[0]))
    # A runaway mask (cap glow) must not become a giant logo. Keep the upper core.
    if int(ys.max() - ys.min()) > head_h * 0.18:
        limit = int(ys.min() + head_h * 0.12)
        keep = mask.copy()
        keep[limit:] = False
        if keep.sum() >= 12:
            mask = keep
            ys, xs = np.where(mask)
    cx = float(xs.mean())
    cy = float(ys.mean())
    glyph_h = max(7, int(head_h * 0.085))
    scale = max(1, glyph_h // 7)
    glyph_w = 7 * scale
    gap = max(1, scale)
    total = glyph_w * 2 + gap
    box_w = int(total * 2.6)
    box_h = int(7 * scale * 2.1)
    x0 = max(0, int(cx - box_w / 2))
    x1 = min(array.shape[1], int(cx + box_w / 2))
    y0 = max(0, int(cy - box_h / 2))
    y1 = min(array.shape[0], int(cy + box_h / 2))
    region = array[y0:y1, x0:x1]
    green = region[:, :, 1].astype(np.int16)
    blue = region[:, :, 2].astype(np.int16)
    red = region[:, :, 0].astype(np.int16)
    bright = (green > 95) & (blue > 140)
    strength = region.max(axis=2)
    cap_like = (strength > 45) & (blue > red + 15) & ~bright
    cap = region[cap_like]
    fill = np.array([18, 96, 190], dtype=np.uint8) if len(cap) == 0 else np.median(cap[:, :3], axis=0).astype(np.uint8)
    region[bright, :3] = fill
    origin_x = int(cx - total / 2)
    origin_y = int(cy - (7 * scale) / 2)
    for index, letter in enumerate("GB"):
        glyph = _GLYPH[letter]
        ox = origin_x + index * (glyph_w + gap)
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit != "1":
                    continue
                py = origin_y + row * scale
                px = ox + col * scale
                if py < 0 or px < 0 or py >= array.shape[0] or px >= array.shape[1]:
                    continue
                yb, xb = min(array.shape[0], py + scale), min(array.shape[1], px + scale)
                array[py:yb, px:xb, 0] = 240
                array[py:yb, px:xb, 1] = 248
                array[py:yb, px:xb, 2] = 255


def mirror_fix_gb(image: Image.Image) -> Image.Image:
    """Mirror a panel and redraw GB so the cap does not show reversed letters."""
    flipped = ImageOps.mirror(image.convert("RGB"))
    array = np.array(flipped)
    mask = _letter_mask(array)
    _paint_gb(array, mask)
    return Image.fromarray(array, "RGB")


def _shift_onto(image: Image.Image, canvas: tuple[int, int], anchor: tuple[int, int]) -> Image.Image:
    src = np.array(image.convert("RGBA"))
    alpha = src[:, :, 3]
    ys, xs = np.where(alpha > 25)
    dst = np.zeros((canvas[1], canvas[0], 4), dtype=np.uint8)
    if len(xs) == 0:
        return Image.fromarray(dst, "RGBA")
    top, bottom = int(ys.min()), int(ys.max())
    band = ys > bottom - max(6, int(0.08 * (bottom - top + 1)))
    cx = float(xs[band].mean()) if band.any() else float(xs.mean())
    cy = float(ys[band].mean()) if band.any() else float(ys.mean())
    ox = int(round(anchor[0] - cx))
    oy = int(round(anchor[1] - cy))
    sh, sw = src.shape[:2]
    dh, dw = dst.shape[:2]
    src_x0 = max(0, -ox)
    src_y0 = max(0, -oy)
    dst_x0 = max(0, ox)
    dst_y0 = max(0, oy)
    width = min(sw - src_x0, dw - dst_x0)
    height = min(sh - src_y0, dh - dst_y0)
    if width > 0 and height > 0:
        dst[dst_y0:dst_y0 + height, dst_x0:dst_x0 + width] = src[src_y0:src_y0 + height, src_x0:src_x0 + width]
    return Image.fromarray(dst, "RGBA")


def _align_all(images: list[Image.Image]) -> list[Image.Image]:
    keyed = [image if image.mode == "RGBA" else key_black(image) for image in images]
    widths = [image.width for image in keyed]
    heights = [image.height for image in keyed]
    canvas = (max(widths) + 40, max(heights) + 30)
    anchor = (canvas[0] // 2, canvas[1] - 28)
    return [_shift_onto(image, canvas, anchor) for image in keyed]


def _side_pair(rgb: Image.Image, native_side: str) -> tuple[Image.Image, Image.Image]:
    """Return (left image, right image) as keyed RGB, before alignment."""
    if native_side == "left":
        return key_black(rgb), key_black(mirror_fix_gb(rgb))
    return key_black(mirror_fix_gb(rgb)), key_black(rgb)


def build_character(character: str) -> CharacterArt:
    fronts_rgb = split_sheet(SOURCE / f"{character}-expressions.jpg")
    turns_rgb = split_sheet(SOURCE / f"{character}-turns.jpg")
    if len(fronts_rgb) != 8 or len(turns_rgb) != 8:
        raise ValueError(f"{character} sheets did not yield 8 panels")
    front = {name: key_black(panel) for name, panel in zip(FRONT_NAMES, fronts_rgb)}
    offsets = [nose_offset(panel) for panel in turns_rgb]
    delta = offsets[3] - offsets[0]
    sequence_side = "left" if delta < 0 else "right"
    notes = [
        f"{character} turn row faces {sequence_side} "
        f"(panel0 {offsets[0]:+.1f}, panel3 {offsets[3]:+.1f})."
    ]
    left_turns: list[tuple[float, Image.Image]] = [(0.0, front["neutral"])]
    right_turns: list[tuple[float, Image.Image]] = [(0.0, front["neutral"])]
    pending_left = [front["neutral"]]
    pending_right = [front["neutral"]]
    turn_left_raw = []
    turn_right_raw = []
    for index, magnitude in enumerate(TURN_MAGNITUDES):
        left_image, right_image = _side_pair(turns_rgb[index], sequence_side)
        turn_left_raw.append((magnitude, left_image))
        turn_right_raw.append((magnitude, right_image))
        pending_left.append(left_image)
        pending_right.append(right_image)
    left_expr_raw: dict[str, Image.Image] = {}
    right_expr_raw: dict[str, Image.Image] = {}
    for index, name in enumerate(TURN_EXPRESSIONS):
        offset = offsets[4 + index] - offsets[0]
        native = "left" if offset < -5 else "right" if offset > 5 else sequence_side
        notes.append(f"{character} {name} native {native} ({offsets[4 + index]:+.1f}).")
        left_image, right_image = _side_pair(turns_rgb[4 + index], native)
        left_expr_raw[name] = left_image
        right_expr_raw[name] = right_image
        pending_left.append(left_image)
        pending_right.append(right_image)
    for name, image in front.items():
        pending_left.append(image)
        pending_right.append(image)
    aligned = _align_all(pending_left + pending_right)
    half = len(pending_left)
    left_aligned = aligned[:half]
    right_aligned = aligned[half:]
    cursor = 0
    left_turns = [(0.0, left_aligned[cursor])]
    right_turns = [(0.0, right_aligned[cursor])]
    cursor += 1
    for magnitude, _image in turn_left_raw:
        left_turns.append((magnitude, left_aligned[cursor]))
        right_turns.append((magnitude, right_aligned[cursor]))
        cursor += 1
    left_expr = {}
    right_expr = {}
    for name in TURN_EXPRESSIONS:
        left_expr[name] = left_aligned[cursor]
        right_expr[name] = right_aligned[cursor]
        cursor += 1
    front_aligned = {}
    for name in FRONT_NAMES:
        front_aligned[name] = left_aligned[cursor]
        cursor += 1
    # The right-side front views are the same pictures; keep one set.
    art = CharacterArt(character, front_aligned, left_turns, right_turns, left_expr, right_expr, notes=notes)
    if character == "male":
        # The turn sheet never reaches a side profile. The approved frame's
        # portrait already points left, brim toward the game. Do not mirror it.
        art.rest_left = frame_rest_pose()
        art.notes.append("male rest pose is the unmirrored approved-frame profile.")
    else:
        rest = left_turns[-1][1]
        if not brim_faces_left(rest):
            rest = key_black(mirror_fix_gb(rest.convert("RGB")))
        art.rest_left = rest
        art.notes.append("female rest pose faces left, brim toward the game.")
    return art


def brim_faces_left(image: Image.Image) -> bool:
    """True when the cap brim extends to the left of the head, toward the game.

    The nose-versus-neck offset measured the wrong side of this portrait.
    The brim is the part that sticks out in the direction the face points.
    """
    array = np.asarray(image.convert("RGBA"))
    # Color, not alpha. A composited well is opaque black, which would hide the brim.
    lit = array[:, :, :3].max(axis=2) > 45
    ys, xs = np.where(lit)
    if len(xs) < 30:
        return False
    top, bottom = int(ys.min()), int(ys.max())
    height = max(1, bottom - top)
    head = ys < top + 0.72 * height
    head_x = xs[head]
    head_y = ys[head]
    if len(head_x) < 30:
        return False
    center = float(head_x.mean())
    cap = head_y < top + 0.30 * height
    if int(cap.sum()) < 10:
        return False
    cap_x = head_x[cap]
    left_reach = center - float(cap_x.min())
    right_reach = float(cap_x.max()) - center
    return left_reach > right_reach


def frame_rest_pose() -> Image.Image:
    """Unmirrored head from the approved SNES frame. The brim already points left.

    The crop is the inner well only. The bezel and its glow stay out of the sprite.
    """
    from .frame_library import FRAME_DIR, PLACEMENTS
    box = PLACEMENTS["snes"]["buddy"]
    image = Image.open(FRAME_DIR / "snes-sky-kingdom.jpg").convert("RGB")
    x, y, w, h = box["x"], box["y"], box["width"], box["height"]
    return key_black(image.crop((x, y, x + w, y + h)))


def get_art(character: str = "male") -> CharacterArt:
    character = "female" if character == "female" else "male"
    if character not in _CACHE:
        _CACHE[character] = build_character(character)
    return _CACHE[character]
