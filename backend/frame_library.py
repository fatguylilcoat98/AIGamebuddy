"""Approved Buddy Overlay frames and the auto-lock geometry.

Each console maps to one frame. The screen rectangle is the irregular opening
left after the rectangular frame is removed. Scenery overhangs that opening.
The footer pad stays in front of the game.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from .config_loader import ROOT
FRAME_DIR = ROOT / "assets" / "frames"
OVERLAY_DIR = FRAME_DIR / "overlays"
RETROARCH_DIR = FRAME_DIR / "retroarch"
ES_DIR = FRAME_DIR / "es-de"
METADATA_PATH = FRAME_DIR / "metadata.json"

# Aliases are the system id Buddy already detects, plus the names Chris uses.
# Add a console by appending a frame entry and its aliases. See the README.
FRAME_FILES = {
    "genesis": "genesis-16bit.png",
    "nes": "nes-8bit-dungeon.png",
    "snes": "snes-sky-kingdom.png",
}

SYSTEM_ALIASES = {
    "genesis": "genesis",
    "megadrive": "genesis",
    "mega drive": "genesis",
    "mega-drive": "genesis",
    "nes": "nes",
    "famicom": "nes",
    "snes": "snes",
    "sfc": "snes",
    "super famicom": "snes",
}

# Portrait and menu, in source pixels of the 2560x1440 art. The live head fills
# the well. The menu opens inside that same frame, so nothing sits under it.
PLACEMENTS = {
    "genesis": {
        "buddy": {"x": 2070, "y": 1024, "width": 412, "height": 224},
        "menu": {"x": 2070, "y": 1174, "width": 412, "height": 74},
    },
    "nes": {
        "buddy": {"x": 2072, "y": 1112, "width": 336, "height": 182},
        "menu": {"x": 2072, "y": 1234, "width": 336, "height": 60},
    },
    "snes": {
        "buddy": {"x": 2166, "y": 1046, "width": 294, "height": 178},
        "menu": {"x": 2166, "y": 1166, "width": 294, "height": 58},
    },
}

DESIGN = {"width": 2560, "height": 1440}
OUTPUTS = {"720p": (1280, 720), "1080p": (1920, 1080)}
# RetroArch's Custom aspect entry. Confirmed as index 23 in current releases.
ASPECT_RATIO_CUSTOM = 23


def frame_for_system(system: str | None) -> str | None:
    if not system:
        return None
    return SYSTEM_ALIASES.get(str(system).strip().lower())


def measure_screen(image: Image.Image, threshold: int = 14) -> dict[str, int]:
    """Largest near-black rectangle, extended down the side gutters under the controller."""
    array = np.asarray(image.convert("RGB"))
    mask = array.max(axis=2) <= threshold
    height, width = mask.shape
    columns = [0] * width
    best = (0, 0, 0, 0, 0)  # area, x, y, w, h
    for y in range(height):
        for x in range(width):
            columns[x] = columns[x] + 1 if mask[y, x] else 0
        stack = [-1]
        for i in range(width + 1):
            column_height = columns[i] if i < width else 0
            while stack[-1] != -1 and columns[stack[-1]] > column_height:
                run_h = columns[stack.pop()]
                run_w = i - stack[-1] - 1
                area = run_h * run_w
                if area > best[0] and run_h > 40 and run_w > 40:
                    best = (area, stack[-1] + 1, y - run_h + 1, run_w, run_h)
            stack.append(i)
    _area, x, y, w, h = best
    if w == 0:
        raise ValueError("No game window found in the frame")

    def column_end(col: int) -> int:
        yy = y + 20
        limit = min(height - 1, y + h + 120)
        while yy < limit and int(array[yy, col].max()) <= threshold + 8:
            yy += 1
        return yy - 1

    bottom = min(column_end(x + max(4, int(w * 0.08))), column_end(x + int(w * 0.92)))
    if bottom < y + h - 1:
        bottom = y + h - 1
    return {"x": int(x), "y": int(y), "width": int(w), "height": int(bottom - y + 1)}


# Design pixels on the 1280x720 art. 1080p is 1.5x these numbers.
# How far the rectangular screen frame extends past the black opening.
# The top band stays short so the title is left alone.
FRAME_BAND = {
    "genesis": {"left": 40, "right": 36, "top": 16, "bottom": 44},
    "nes": {"left": 26, "right": 26, "top": 30, "bottom": 26},
    "snes": {"left": 24, "right": 22, "top": 14, "bottom": 20},
}
# Footer pads in the approved art. The pad is restored; the frame behind it is not.
CONTROLLER_RECT = {
    "genesis": {"x": 518, "y": 648, "width": 296, "height": 54},
    "nes": {"x": 448, "y": 576, "width": 382, "height": 108},
    "snes": {"x": 452, "y": 562, "width": 364, "height": 132},
}


def buddy_well_rect(image: Image.Image, frame_id: str) -> dict[str, int]:
    """The black portrait plate. It stays the authored rectangle so it cannot swallow the opening."""
    box = PLACEMENTS[frame_id]["buddy"]
    width, height = image.size
    x = max(0, min(int(box["x"]), width - 1))
    y = max(0, min(int(box["y"]), height - 1))
    return {
        "x": x,
        "y": y,
        "width": max(1, min(int(box["width"]), width - x)),
        "height": max(1, min(int(box["height"]), height - y)),
    }


def clear_painted_head(image: Image.Image, frame_id: str) -> Image.Image:
    """Replace a baked hologram with the well's dark plate. The opening's alpha stays."""
    rgba = np.array(image.convert("RGBA")).copy()
    rect = buddy_well_rect(image, frame_id)
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    sample = rgba[y:y + h, x:x + w, :3]
    dark = sample.max(axis=2) <= 40
    if dark.any():
        color = np.median(sample[dark], axis=0).astype(np.uint8)
    else:
        color = np.array([0, 0, 10], dtype=np.uint8)
    rgba[y:y + h, x:x + w, :3] = color
    return Image.fromarray(rgba, "RGBA")


def hologram_blue_pixels(image: Image.Image, rect: dict[str, int]) -> int:
    """Bright cyan pixels. The empty well should have none before the live sprite."""
    array = np.asarray(image.convert("RGB"))
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    region = array[y + 2:y + h - 2, x + 2:x + w - 2]
    red = region[:, :, 0].astype(np.int16)
    green = region[:, :, 1].astype(np.int16)
    blue = region[:, :, 2].astype(np.int16)
    glow = (blue > 90) & (blue > red + 40) & (green > 30)
    return int(glow.sum())


def controller_top(image: Image.Image, screen: dict[str, int]) -> int:
    """Highest row of the footer controller inside the measured black window."""
    array = np.asarray(image.convert("RGB"))
    x, y, w, h = screen["x"], screen["y"], screen["width"], screen["height"]
    left, right = x + w // 3, x + (2 * w) // 3
    found = None
    for row in range(y + h - 1, y + h // 2, -1):
        if int(array[row, left:right].max()) > 40:
            found = row
        elif found is not None:
            break
    return found if found is not None else y + h - 1


def _dilate(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, constant_values=False)
    grown = np.zeros(mask.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= padded[1 + dy:padded.shape[0] - 1 + dy, 1 + dx:padded.shape[1] - 1 + dx]
    return grown


def _nearest_outside(inside: np.ndarray, limit: int = 48) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Distance to the nearest pixel that is not inside, and that pixel's coordinates."""
    height, width = inside.shape
    dist = np.where(inside, np.int16(9999), np.int16(0))
    source_y = np.full((height, width), -1, np.int16)
    source_x = np.full((height, width), -1, np.int16)
    ys, xs = np.where(~inside)
    source_y[ys, xs] = ys.astype(np.int16)
    source_x[ys, xs] = xs.astype(np.int16)
    neighbors = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
    for _ in range(limit):
        changed = False
        for dy, dx in neighbors:
            y0s, y1s = max(0, dy), height + min(0, dy)
            x0s, x1s = max(0, dx), width + min(0, dx)
            y0d, y1d = max(0, -dy), height + min(0, -dy)
            x0d, x1d = max(0, -dx), width + min(0, -dx)
            src = dist[y0s:y1s, x0s:x1s]
            dst = dist[y0d:y1d, x0d:x1d]
            better = src + 1 < dst
            if not better.any():
                continue
            changed = True
            dst[better] = src[better] + 1
            dist[y0d:y1d, x0d:x1d] = dst
            source_y[y0d:y1d, x0d:x1d][better] = source_y[y0s:y1s, x0s:x1s][better]
            source_x[y0d:y1d, x0d:x1d][better] = source_x[y0s:y1s, x0s:x1s][better]
        if not changed:
            break
    return dist, source_y, source_x


def _protected(image: Image.Image, frame_id: str, raw: dict[str, int]) -> np.ndarray:
    """Buddy's well, the menu, and the title letters stay opaque and clickable.

    The sky between the title and the game is not protected, so the opening
    can wander through it instead of stopping on a straight line.
    """
    height, width = image.size[1], image.size[0]
    mask = np.zeros((height, width), dtype=bool)
    rgb = np.asarray(image.convert("RGB"))
    lum = rgb.max(axis=2)
    letters = np.zeros_like(mask)
    top = int(raw["y"]) + 2
    bright = lum[:top, :] > 168
    span = bright[:, int(raw["x"]):int(raw["x"]) + int(raw["width"])]
    if span.shape[1]:
        # The old frame's highlight is a bright row across the whole opening.
        # Title letters never fill that much of a row. Clear the row and its edge.
        hot = span.mean(axis=1) > 0.4
        expanded = hot.copy()
        for shift in (1, 2):
            expanded[shift:] |= hot[:-shift]
            expanded[:-shift] |= hot[shift:]
        bright[expanded, :] = False
    letters[:top, :] = bright
    for _ in range(2):
        letters = _dilate(letters)
    # Only the letter shapes. A full-width band would put a straight edge under the title.
    mask |= letters
    well = buddy_well_rect(image, frame_id)
    menu = PLACEMENTS[frame_id]["menu"]
    for rect, pad in ((well, 8), (menu, 4)):
        x0 = max(0, int(rect["x"]) - pad)
        y0 = max(0, int(rect["y"]) - pad)
        x1 = min(width, int(rect["x"]) + int(rect["width"]) + pad)
        y1 = min(height, int(rect["y"]) + int(rect["height"]) + pad)
        mask[y0:y1, x0:x1] = True
    return mask


def _controller_pixels(rgb: np.ndarray, frame_id: str) -> np.ndarray:
    """The footer pad, not the black around it and not the frame it sits on."""
    height, width = rgb.shape[:2]
    rect = CONTROLLER_RECT[frame_id]
    mask = np.zeros((height, width), dtype=bool)
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    mask[y:y + h, x:x + w] = True
    lum = rgb.max(axis=2)
    mask &= lum > 28
    return mask


def opening_mask(image: Image.Image, frame_id: str, raw: dict[str, int] | None = None) -> np.ndarray:
    """Transparent game opening: the black window, the rectangular frame, and a wavy bite.

    Scenery, the footer pad, Buddy, and the menu are not part of the mask.
    """
    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    raw = raw or measure_screen(image)
    x, y, w, h = raw["x"], raw["y"], raw["width"], raw["height"]
    lum = rgb.max(axis=2)
    black = lum <= 18
    near = np.zeros_like(black)
    near[max(0, y - 2):min(height, y + h + 2), max(0, x - 2):min(width, x + w + 2)] = True
    opening = black & near
    opening[y:y + h, x:x + w] = True
    dist, _oy, _ox = _nearest_outside(~opening, 52)
    band = FRAME_BAND[frame_id]
    ys, xs = np.mgrid[0:height, 0:width]
    # Direction comes from the nearest black pixel, so each side uses its own thickness.
    # `_nearest_outside(~opening)` points at the opening. Recover it with a second pass
    # only where we need the side. The distance alone is not directional, so split by
    # which edge of the measured window the pixel sits on.
    left = xs < x
    right = xs >= x + w
    above = ys < y
    below = ys >= y + h
    limit = np.full(rgb.shape[:2], 0, np.int16)
    limit[left] = band["left"]
    limit[right] = band["right"]
    limit[above & ~left & ~right] = band["top"]
    limit[below & ~left & ~right] = band["bottom"]
    # Corners take the larger neighboring band so the rounded frame is fully covered.
    limit[above & left] = max(band["top"], band["left"])
    limit[above & right] = max(band["top"], band["right"])
    limit[below & left] = max(band["bottom"], band["left"])
    limit[below & right] = max(band["bottom"], band["right"])
    bezel = opening | ((dist > 0) & (dist <= limit))
    protect = _protected(image, frame_id, raw)
    pad = _controller_pixels(rgb, frame_id)
    bezel &= ~protect & ~pad
    outside, _, _ = _nearest_outside(~bezel, 24)
    yy, xx = np.where(bezel)
    if len(xx) == 0:
        return bezel
    x0, x1 = int(xx.min()), int(xx.max())
    y0, y1 = int(yy.min()), int(yy.max())
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)
    nx = (xs - x0) / bw
    ny = (ys - y0) / bh
    corner = np.clip(1.0 - (np.minimum(nx, 1 - nx) + np.minimum(ny, 1 - ny)) * 3.8, 0, 1)
    wave = 0.5 + 0.5 * (
        0.45 * np.sin(xs * 0.05 + 0.6)
        + 0.35 * np.sin(ys * 0.07 + 1.3)
        + 0.20 * np.sin(xs * 0.16 + ys * 0.11 + 2.2)
    )
    bite = 7.0 + 16.0 * wave + 8.0 * corner
    hole = bezel | ((outside > 0) & (outside <= bite) & ~protect & ~pad)
    # The frame highlight is a bright row just above the black window.
    # Leave the title above that row alone. The highlight itself is removed.
    span = lum[:, x:x + w] > 140
    frame_row = int(y)
    seen_frame = False
    for row in range(int(y), max(0, int(y) - 36), -1):
        bright_row = bool(span.shape[1]) and float(span[row].mean()) > 0.45
        if bright_row:
            frame_row = row
            seen_frame = True
        elif seen_frame:
            break
    if seen_frame and frame_row < y:
        x_lo = max(0, int(x) - 8)
        x_hi = min(width, int(x) + int(w) + 8)
        hole[:frame_row, x_lo:x_hi] = False
    menu = PLACEMENTS[frame_id]["menu"]
    well = buddy_well_rect(image, frame_id)
    # The game rectangle has to stay off the menu. The menu sits on the right,
    # so the opening stops a few pixels before it.
    limit_x = min(int(menu["x"]), int(well["x"])) - 4
    hole[:, limit_x:] = False
    # Drop transparent specks that are not attached to the game opening.
    seen = opening.copy()
    frontier = opening
    for _ in range(72):
        nxt = _dilate(frontier) & hole & ~seen
        if not nxt.any():
            break
        seen |= nxt
        frontier = nxt
    return seen


def _scenery_overhang(rgb: np.ndarray, hole: np.ndarray, protect: np.ndarray) -> np.ndarray:
    """Pull real scenery in over the opening. Dark sky and frame colors stay out."""
    height, width = rgb.shape[:2]
    inside, near_y, near_x = _nearest_outside(hole, 32)
    inside = np.where(hole, inside, 0)
    ys, xs = np.where(hole)
    if len(xs) == 0:
        return hole, ys, xs
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    grid_y, grid_x = np.mgrid[0:height, 0:width]
    nx = (grid_x - x0) / max(1, x1 - x0)
    ny = (grid_y - y0) / max(1, y1 - y0)
    corner = np.clip(1.0 - (np.minimum(nx, 1 - nx) + np.minimum(ny, 1 - ny)) * 3.8, 0, 1)
    wave = 0.5 + 0.5 * (
        0.45 * np.sin(grid_x * 0.05 + 0.8)
        + 0.35 * np.sin(grid_y * 0.08 + 0.4)
        + 0.20 * np.sin(grid_x * 0.15 + grid_y * 0.1)
    )
    span = float(min(x1 - x0, y1 - y0))
    depth = np.clip(span * (0.010 + 0.016 * corner) * (0.45 + 0.55 * wave), 5, 20)
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    lum = np.maximum(np.maximum(red, green), blue)
    scenic = (lum >= 64) | ((green > 75) & (green > blue + 12)) | ((red > 100) & (red > blue + 18))
    # Screen-frame glow is blue-dominant or purple. Waterfalls stay, they are bright green too.
    frame_blue = (blue > red + 12) & (blue > green + 8) & (blue > 55) & (green < 150)
    frame_purple = (red > 110) & (blue > 100) & (green + 25 < red) & (green + 15 < blue)
    scenic &= ~frame_blue & ~frame_purple
    overhang = hole & (inside > 0) & (inside <= depth) & (near_y >= 0) & ~protect
    step = np.clip(depth - inside, 0, 16)
    mag = np.maximum(inside, 1).astype(np.float32)
    ux = (near_x.astype(np.float32) - grid_x) / mag
    uy = (near_y.astype(np.float32) - grid_y) / mag
    sample_x = np.clip(np.rint(near_x + ux * step).astype(np.int32), 0, width - 1)
    sample_y = np.clip(np.rint(near_y + uy * step).astype(np.int32), 0, height - 1)
    ok = (~hole[sample_y, sample_x]) & scenic[sample_y, sample_x] & ~protect[sample_y, sample_x]
    paint = overhang & ok
    return paint, sample_y, sample_x


def authored_opening(image: Image.Image) -> np.ndarray | None:
    """The transparent game hole, when the art already has one."""
    if image.mode != "RGBA":
        return None
    hole = np.asarray(image)[:, :, 3] < 16
    if int(hole.sum()) < int(hole.size * 0.15):
        return None
    return hole


def _bbox(mask: np.ndarray) -> dict[str, int]:
    ys, xs = np.where(mask)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return {"x": x0, "y": y0, "width": x1 - x0 + 1, "height": y1 - y0 + 1}


def enlarge_screen(image: Image.Image, frame_id: str, raw: dict[str, int] | None = None) -> dict[str, int]:
    """Bounding box of the transparent opening. The pad and the menu stay outside it."""
    authored = authored_opening(image)
    if authored is not None:
        return _bbox(authored)
    raw = raw or measure_screen(image)
    hole = opening_mask(image, frame_id, raw)
    ys, xs = np.where(hole)
    if len(xs) == 0:
        return raw
    return _bbox(hole)


def cut_hole(image: Image.Image, screen: dict[str, int], lip: int = 0,
             bottom_keep: int = 0, frame_id: str | None = None) -> Image.Image:
    """Remove the rectangular screen frame and lay scenery over the irregular edge.

    `screen`, `lip`, and `bottom_keep` stay in the signature for older callers.
    The opening is measured from the art. There is no drawn bezel to paint back.
    """
    del screen, lip, bottom_keep
    if frame_id is None:
        frame_id = "genesis"
    original = np.array(image.convert("RGBA"))
    rgb = original[:, :, :3]
    raw = measure_screen(image)
    hole = opening_mask(image, frame_id, raw)
    protect = _protected(image, frame_id, raw)
    output = original.copy()
    output[hole, 3] = 0
    paint, sample_y, sample_x = _scenery_overhang(rgb, hole, protect)
    output[paint, :3] = rgb[sample_y[paint], sample_x[paint]]
    output[paint, 3] = 255
    _cover_frame_beside_buddy(output, image, frame_id, raw)
    return Image.fromarray(output, "RGBA")


def _cover_frame_beside_buddy(output: np.ndarray, image: Image.Image, frame_id: str,
                              raw: dict[str, int]) -> None:
    """The menu starts where the old right-hand frame still is. Paint that strip with scenery.

    The opening itself stops before the menu so the game rectangle cannot cover it.
    """
    menu = PLACEMENTS[frame_id]["menu"]
    well = buddy_well_rect(image, frame_id)
    limit_x = min(int(menu["x"]), int(well["x"])) - 4
    stop = int(well["x"]) - 2
    if limit_x >= stop:
        return
    red = output[:, :, 0].astype(np.int16)
    green = output[:, :, 1].astype(np.int16)
    blue = output[:, :, 2].astype(np.int16)
    chrome = (blue > red + 12) & (blue > green + 8) & (blue > 70)
    purple = (red > 110) & (blue > 100) & (green + 20 < red) & (green + 10 < blue)
    frame = chrome | purple
    cy = int(raw["y"] + raw["height"] // 2)
    donor = None
    for x in range(limit_x + 8, stop):
        if not frame[cy, x]:
            donor = x
            break
    if donor is None:
        return
    take = frame[:, limit_x:donor]
    if not take.any():
        return
    copied = output[:, donor, :].copy()
    for x in range(limit_x, donor):
        column = take[:, x - limit_x]
        output[column, x] = copied[column]


def scale_rect(rect: dict[str, int], target: tuple[int, int]) -> dict[str, int]:
    sx = target[0] / DESIGN["width"]
    sy = target[1] / DESIGN["height"]
    return {
        "x": int(round(rect["x"] * sx)),
        "y": int(round(rect["y"] * sy)),
        "width": int(round(rect["width"] * sx)),
        "height": int(round(rect["height"] * sy)),
    }


def paste_head(image: Image.Image, head: Image.Image, box: dict[str, int]) -> Image.Image:
    """Center a head in the well. The ring stays fully inside, with room above the cap.

    The same padding is used for both characters, on every frame.
    """
    canvas = image.convert("RGBA")
    x, y, w, h = int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"])
    if w < 2 or h < 2:
        return canvas
    sprite = head.convert("RGBA")
    box_px = sprite.getbbox()
    trimmed = sprite.crop(box_px) if box_px else sprite
    # Fill most of the well height. A wide profile is center-cropped, not shrunk away.
    target_h = max(8, int(round(h * 0.88)))
    scale = target_h / max(1, trimmed.height)
    resized = trimmed.resize(
        (max(1, int(round(trimmed.width * scale))), target_h),
        Image.Resampling.LANCZOS,
    )
    if resized.width > w:
        left = (resized.width - w) // 2
        resized = resized.crop((left, 0, left + w, resized.height))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ox = (w - resized.width) // 2
    oy = (h - resized.height) // 2
    layer.alpha_composite(resized, (ox, oy))
    canvas.alpha_composite(layer, (x, y))
    return canvas


def punch_screen(image: Image.Image, screen: dict[str, int], threshold: int = 18,
                 frame_id: str | None = None) -> Image.Image:
    """Keep an authored alpha opening. Older art still gets the measured cut.

    `threshold` and `screen` stay so older callers remain valid.
    """
    del threshold
    if authored_opening(image) is not None:
        return image.convert("RGBA")
    return cut_hole(image, screen, frame_id=frame_id or "genesis")


def build_metadata() -> dict:
    frames = {}
    for frame_id, filename in FRAME_FILES.items():
        path = FRAME_DIR / filename
        source = Image.open(path)
        screen = enlarge_screen(source, frame_id)
        placement = PLACEMENTS[frame_id]
        viewports = {name: scale_rect(screen, size) for name, size in OUTPUTS.items()}
        frames[frame_id] = {
            "file": filename,
            "systems": [alias for alias, target in SYSTEM_ALIASES.items() if target == frame_id],
            "screen": screen,
            "well": buddy_well_rect(source, frame_id),
            "buddy": placement["buddy"],
            "menu": placement["menu"],
            "viewports": viewports,
        }
    return {
        "product_name": "Buddy Overlay",
        "tagline": "Retro games, real attitude",
        "design": DESIGN,
        "frames": frames,
    }


def load_metadata() -> dict:
    if METADATA_PATH.exists():
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return build_metadata()


def frame_record(frame_id: str) -> dict:
    data = load_metadata()["frames"][frame_id]
    return data


def retroarch_overlay_cfg(frame_id: str) -> str:
    record = frame_record(frame_id)
    png_name = Path(record["file"]).stem + ".png"
    return (
        "overlays = 1\n"
        f"overlay0_overlay = \"{png_name}\"\n"
        "overlay0_full_screen = true\n"
        "overlay0_descs = 0\n"
    )


def retroarch_viewport_cfg(frame_id: str, mode: str, overlay_cfg: str) -> str:
    viewport = frame_record(frame_id)["viewports"][mode]
    return "\n".join([
        "video_scale_integer = \"false\"",
        f"aspect_ratio_index = \"{ASPECT_RATIO_CUSTOM}\"",
        f"custom_viewport_x = \"{viewport['x']}\"",
        f"custom_viewport_y = \"{viewport['y']}\"",
        f"custom_viewport_width = \"{viewport['width']}\"",
        f"custom_viewport_height = \"{viewport['height']}\"",
        "input_overlay_enable = \"true\"",
        "input_overlay_auto_scale = \"true\"",
        "input_overlay_hide_in_menu = \"false\"",
        f"input_overlay = \"{overlay_cfg}\"",
        "",
    ])


def es_de_snippet(overlay_root: Path) -> str:
    lines = [
        "<!-- Drop the <system> blocks you need into ES-DE's es_systems.xml. -->",
        "<!-- %ROM% and the core path are yours. The appendconfig locks the viewport. -->",
    ]
    for frame_id, record in load_metadata()["frames"].items():
        for system in record["systems"]:
            cfg = f"assets/frames/retroarch/{frame_id}-1080p.cfg"
            lines.append(
                f"<!-- {system} -> {frame_id} -->\n"
                f"<!-- retroarch -L CORE --fullscreen --appendconfig \"{cfg}\" \"%ROM%\" -->"
            )
    return "\n".join(lines) + "\n"


def write_outputs() -> list[Path]:
    """Write metadata, transparent overlays, and RetroArch/ES-DE config."""
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    RETROARCH_DIR.mkdir(parents=True, exist_ok=True)
    ES_DIR.mkdir(parents=True, exist_ok=True)
    metadata = build_metadata()
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    written = [METADATA_PATH]
    for frame_id, record in metadata["frames"].items():
        source = clear_painted_head(Image.open(FRAME_DIR / record["file"]), frame_id)
        png_name = Path(record["file"]).stem + ".png"
        png_path = OVERLAY_DIR / png_name
        punch_screen(source, record["screen"], frame_id=frame_id).save(png_path)
        cfg_path = OVERLAY_DIR / f"{frame_id}.cfg"
        cfg_path.write_text(retroarch_overlay_cfg(frame_id), encoding="utf-8")
        written.extend((png_path, cfg_path))
        for mode in OUTPUTS:
            viewport_path = RETROARCH_DIR / f"{frame_id}-{mode}.cfg"
            # Path RetroArch can resolve when this cfg is passed with --appendconfig.
            overlay_ref = f"../overlays/{frame_id}.cfg"
            viewport_path.write_text(
                retroarch_viewport_cfg(frame_id, mode, overlay_ref),
                encoding="utf-8",
            )
            written.append(viewport_path)
    es_path = ES_DIR / "launch-commands.txt"
    es_path.write_text(es_de_snippet(FRAME_DIR), encoding="utf-8")
    written.append(es_path)
    return written


def detect_display_size() -> tuple[int, int] | None:
    """Current primary monitor, or None when it cannot be read."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
    except Exception:
        return None
    if width < 640 or height < 480:
        return None
    return width, height


def write_runtime_retroarch_cfg(frame_id: str, size: tuple[int, int], directory: Path) -> Path:
    """Viewport scaled to `size`, with absolute overlay paths.

    RetroArch resolves a relative input_overlay from the process working
    directory, so the cfg written here does not use `../overlays`. Exclusive
    fullscreen is off. Windowed fullscreen uses this exact resolution; a 720p
    viewport on a different window puts the game outside the hole.
    """
    directory.mkdir(parents=True, exist_ok=True)
    record = frame_record(frame_id)
    viewport = scale_rect(record["screen"], size)
    png = (OVERLAY_DIR / (Path(record["file"]).stem + ".png")).resolve()
    if not png.exists():
        source = clear_painted_head(Image.open(FRAME_DIR / record["file"]), frame_id)
        OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
        punch_screen(source, record["screen"], frame_id=frame_id).save(png)
    overlay_path = directory / f"{frame_id}-overlay.cfg"
    overlay_path.write_text(
        "\n".join([
            "overlays = 1",
            f'overlay0_overlay = "{png.as_posix()}"',
            "overlay0_full_screen = true",
            "overlay0_descs = 0",
            "",
        ]),
        encoding="utf-8",
    )
    width, height = size
    cfg_path = directory / f"{frame_id}-{width}x{height}.cfg"
    cfg_path.write_text(
        "\n".join([
            'video_fullscreen = "false"',
            'video_windowed_fullscreen = "true"',
            f'video_window_width = "{width}"',
            f'video_window_height = "{height}"',
            'video_scale_integer = "false"',
            f'aspect_ratio_index = "{ASPECT_RATIO_CUSTOM}"',
            f'custom_viewport_x = "{viewport["x"]}"',
            f'custom_viewport_y = "{viewport["y"]}"',
            f'custom_viewport_width = "{viewport["width"]}"',
            f'custom_viewport_height = "{viewport["height"]}"',
            'input_overlay_enable = "true"',
            'input_overlay_auto_scale = "true"',
            'input_overlay_hide_in_menu = "false"',
            f'input_overlay = "{overlay_path.resolve().as_posix()}"',
            "",
        ]),
        encoding="utf-8",
    )
    return cfg_path


def install_retroarch_configs(directory: Path | None = None) -> list[Path]:
    """Write absolute-path configs for 720p, 1080p, and the current display."""
    target = directory or (FRAME_DIR / "retroarch")
    written = []
    sizes = [(1280, 720), (1920, 1080)]
    detected = detect_display_size()
    if detected and detected not in sizes:
        sizes.append(detected)
    for frame_id in FRAME_FILES:
        for size in sizes:
            written.append(write_runtime_retroarch_cfg(frame_id, size, target))
    return written


def append_config_for(frame_id: str, mode: str = "1080p") -> Path:
    path = RETROARCH_DIR / f"{frame_id}-{mode}.cfg"
    if not path.exists():
        write_outputs()
    return path


def scaled_screen(frame_id: str, window: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if frame_id not in FRAME_FILES:
        return None
    rect = scale_rect(frame_record(frame_id)["screen"], window)
    return rect["x"], rect["y"], rect["width"], rect["height"]


def scaled_box(frame_id: str, key: str, window: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if frame_id not in FRAME_FILES:
        return None
    rect = scale_rect(frame_record(frame_id)[key], window)
    return rect["x"], rect["y"], rect["width"], rect["height"]


if __name__ == "__main__":
    if "--install" in sys.argv:
        for path in install_retroarch_configs():
            print(path)
    else:
        for path in write_outputs():
            print(path)
