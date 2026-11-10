"""Chris's Super NES frame, turned into the overlay.

The source is his 1671x941 painting. It is scaled to the 2560x1440 design
with Lanczos, the black opening connected to the center becomes the game
hole, and the black rectangle inside the bottom-right BUDDY box is where
the hologram sits.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .config_loader import ROOT

SOURCE_PATH = ROOT / "assets" / "frames" / "authored" / "chris-snes-frame-v2.png"
DESIGN = (2560, 1440)
# Top-left control. It sits on the city art, above the opening.
HAMBURGER = {"x": 36, "y": 24, "width": 220, "height": 132}

_CACHE: dict[tuple, dict] = {}


def _flood(mask: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
    """Scanline flood fill. `mask` is not modified."""
    height, width = mask.shape
    seen = np.zeros((height, width), dtype=np.uint8)
    sy, sx = int(seed[0]), int(seed[1])
    if not (0 <= sy < height and 0 <= sx < width) or not mask[sy, sx]:
        return seen.astype(bool)
    stack = [(sy, sx)]
    seen[sy, sx] = 1
    while stack:
        y, x = stack.pop()
        xl = x
        while xl > 0 and mask[y, xl - 1] and not seen[y, xl - 1]:
            xl -= 1
            seen[y, xl] = 1
        xr = x
        while xr + 1 < width and mask[y, xr + 1] and not seen[y, xr + 1]:
            xr += 1
            seen[y, xr] = 1
        for yy in (y - 1, y + 1):
            if yy < 0 or yy >= height:
                continue
            xx = xl
            while xx <= xr:
                if mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = 1
                    stack.append((yy, xx))
                    while xx <= xr and (not mask[yy, xx] or seen[yy, xx]):
                        xx += 1
                else:
                    xx += 1
    return seen.astype(bool)


def _largest_rect(mask: np.ndarray, min_side: int = 40) -> dict[str, int] | None:
    height, width = mask.shape
    columns = np.zeros(width, dtype=np.int32)
    best = (0, 0, 0, 0, 0)
    for y in range(height):
        columns = np.where(mask[y], columns + 1, 0)
        stack = [-1]
        for i in range(width + 1):
            column_height = int(columns[i]) if i < width else 0
            while stack[-1] != -1 and int(columns[stack[-1]]) > column_height:
                run_h = int(columns[stack.pop()])
                run_w = i - stack[-1] - 1
                area = run_h * run_w
                if area > best[0] and run_h >= min_side and run_w >= min_side:
                    best = (area, stack[-1] + 1, y - run_h + 1, run_w, run_h)
            stack.append(i)
    if best[0] == 0:
        return None
    _area, x, y, w, h = best
    return {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    grown = mask.copy()
    for _ in range(radius):
        padded = np.pad(grown, 1, constant_values=False)
        nxt = np.zeros(grown.shape, dtype=bool)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nxt |= padded[1 + dy:padded.shape[0] - 1 + dy, 1 + dx:padded.shape[1] - 1 + dx]
        grown = nxt
    return grown


def _rect_mask(shape: tuple[int, int], rect: dict[str, int], pad: int = 0) -> np.ndarray:
    height, width = shape
    mask = np.zeros(shape, dtype=bool)
    x0 = max(0, int(rect["x"]) - pad)
    y0 = max(0, int(rect["y"]) - pad)
    x1 = min(width, int(rect["x"]) + int(rect["width"]) + pad)
    y1 = min(height, int(rect["y"]) + int(rect["height"]) + pad)
    mask[y0:y1, x0:x1] = True
    return mask


def _signature(image: Image.Image) -> tuple:
    array = np.asarray(image)
    flat = array.reshape(-1)
    step = max(1, flat.size // 5000)
    return (image.size, image.mode, int(flat[::step].sum()), int(array.shape[-1]) if array.ndim == 3 else 1)


def measure_snes_art(image: Image.Image) -> dict[str, dict[str, int]]:
    """Game rectangle, Buddy's black well, and the hamburger button."""
    key = _signature(image)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    rgba = image.convert("RGBA")
    array = np.asarray(rgba)
    rgb = array[:, :, :3]
    alpha = array[:, :, 3]
    lum = rgb.max(axis=2)
    height, width = lum.shape
    authored = alpha < 16
    if int(authored.sum()) > int(authored.size * 0.08):
        hole = authored
    else:
        dark = lum <= 18
        hole = _flood(dark, (height // 2, width // 2))
    game = _largest_rect(hole)
    if game is None:
        raise ValueError("Chris's SNES frame has no game opening")
    # Keep the art's irregular edge, and drop dark gutters far from that opening
    # (the cracks around the BUDDY plaque must not become the game hole).
    near = _dilate(_rect_mask((height, width), game, pad=0), 42) | _rect_mask((height, width), game)
    hole = hole & near
    game = _largest_rect(hole) or game
    blocked = _rect_mask((height, width), game, pad=8)
    blocked |= _rect_mask((height, width), HAMBURGER, pad=4)
    search = np.zeros_like(hole)
    search[int(height * 0.55):, int(width * 0.68):] = True
    buddy_dark = (lum <= 14) & ~hole & search & ~blocked
    buddy = _largest_rect(buddy_dark, min_side=80)
    if buddy is None:
        raise ValueError("Chris's SNES frame has no Buddy box")
    result = {"game": game, "buddy": buddy, "hamburger": dict(HAMBURGER), "hole_pixels": int(hole.sum())}
    _CACHE[key] = result
    return result


def _feather(rgb: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """1–2px alpha ramp on the dark edge. Bright art stays solid."""
    alpha = np.full(hole.shape, 255, dtype=np.uint8)
    alpha[hole] = 0
    outside = ~hole
    inner = _dilate(outside, 1) & hole
    inner2 = _dilate(outside, 2) & hole & ~inner
    ring = _dilate(hole, 1) & outside
    ring2 = _dilate(hole, 2) & outside & ~ring
    lum = rgb.max(axis=2)
    dark = lum <= 42
    alpha[inner2] = 28
    alpha[inner] = 96
    alpha[ring & dark] = 176
    alpha[ring2 & dark] = 220
    return alpha


def render_snes_frame(source: Image.Image | None = None) -> tuple[Image.Image, dict]:
    """Scale Chris's painting and cut the opening. Returns art plus rectangles."""
    plate = source if source is not None else Image.open(SOURCE_PATH)
    scaled = plate.convert("RGB").resize(DESIGN, Image.Resampling.LANCZOS)
    rgb = np.asarray(scaled)
    lum = rgb.max(axis=2)
    height, width = lum.shape
    hole = _flood(lum <= 18, (height // 2, width // 2))
    game = _largest_rect(hole)
    if game is None:
        raise ValueError("No game opening after scaling")
    near = _dilate(_rect_mask((height, width), game), 42)
    hole = hole & near
    game = _largest_rect(hole) or game
    alpha = _feather(rgb, hole)
    # The Buddy well stays opaque black so the hologram has a plate to sit on.
    out = np.dstack([rgb, alpha])
    image = Image.fromarray(out, "RGBA")
    measured = measure_snes_art(image)
    return image, measured


def write_snes_frame(path: Path | None = None) -> dict:
    image, measured = render_snes_frame()
    dest = path or (ROOT / "assets" / "frames" / "snes-sky-kingdom.png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="PNG", optimize=True)
    _CACHE.clear()
    return measured
