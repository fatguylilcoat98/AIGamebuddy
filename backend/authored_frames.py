"""Turn the authored scenery plates into Buddy frames.

The plates are original pixel art with a flat magenta game opening. This
module keys that opening, drops loose objects that would sit on the game,
and paints Buddy's own labels. Sega, Nintendo, and Zion never appear.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .config_loader import ROOT

AUTHORED = ROOT / "assets" / "frames" / "authored"
OUTPUT = {
    "nes": ROOT / "assets" / "frames" / "nes-8bit-dungeon.png",
    "snes": ROOT / "assets" / "frames" / "snes-sky-kingdom.png",
    "genesis": ROOT / "assets" / "frames" / "genesis-16bit.png",
}

# 5x7 glyphs. Rows are left to right, 1 is ink.
_FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10001", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ",": ["00000", "00000", "00000", "00000", "00100", "00100", "01000"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
}

# Inner plaque of each title banner, in the 1280x720 plate.
PLAQUES = {
    "nes": (534, 28, 210, 30),
    "snes": (524, 24, 230, 32),
    "genesis": (446, 16, 380, 30),
}
SUBTITLE = {
    "nes": "8-BIT",
    "snes": "16-BIT",
    "genesis": "16-BIT",
}
INK = {
    "nes": (255, 214, 140, 255),
    "snes": (255, 236, 255, 255),
    "genesis": (186, 232, 255, 255),
}


def _dilate(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, constant_values=False)
    grown = np.zeros(mask.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= padded[1 + dy:padded.shape[0] - 1 + dy, 1 + dx:padded.shape[1] - 1 + dx]
    return grown


def _component_from(mask: np.ndarray, seed: tuple[int, int], limit: int = 900) -> np.ndarray:
    height, width = mask.shape
    seen = np.zeros_like(mask)
    y, x = seed
    if not mask[y, x]:
        # Walk to the nearest masked pixel.
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return seen
        nearest = np.argmin(np.abs(ys - y) + np.abs(xs - x))
        y, x = int(ys[nearest]), int(xs[nearest])
    frontier = np.zeros_like(mask)
    frontier[y, x] = True
    seen[y, x] = True
    for _ in range(limit):
        nxt = _dilate(frontier) & mask & ~seen
        if not nxt.any():
            break
        seen |= nxt
        frontier = nxt
    return seen


def _magenta_hole(rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    sample = rgb[height // 2, width // 2].astype(np.int16)
    delta = np.abs(rgb.astype(np.int16) - sample).sum(axis=2)
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    # The key color, including jpeg blocks that drifted off the center sample.
    pink = (red > 185) & (green < 90) & (blue > 90) & (red > green + 80)
    rough = (delta <= 100) | pink
    hole = _component_from(rough, (height // 2, width // 2))
    fringe = (delta <= 160) & _dilate(hole) & ~hole
    hole = hole | fringe
    # A few pink blocks sit just off the opening. Pull in any pink that touches it.
    for _ in range(6):
        hole = hole | (pink & _dilate(hole))
    return hole


def _clear_floating_rings(rgb: np.ndarray, frame_id: str) -> None:
    """Small gold circles read as a mascot. A coin pile is much larger and stays."""
    if frame_id == "genesis":
        red = rgb[:, :, 0].astype(np.int16)
        green = rgb[:, :, 1].astype(np.int16)
        blue = rgb[:, :, 2].astype(np.int16)
        bright = (red > 180) & (green > 100) & (blue < 140) & (red > blue + 40)
        height, width = bright.shape
        seen = np.zeros_like(bright)
        disks = []
        ys, xs = np.where(bright)
        for y, x in zip(ys.tolist(), xs.tolist()):
            if seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            pixels = []
            while stack:
                cy, cx = stack.pop()
                pixels.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and bright[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(pixels) < 80:
                continue
            yy = [p[0] for p in pixels]
            xx = [p[1] for p in pixels]
            if max(yy) - min(yy) > 40 or max(xx) - min(xx) > 40:
                continue
            disk = np.zeros_like(bright)
            y0, y1 = max(0, min(yy) - 8), min(height, max(yy) + 9)
            x0, x1 = max(0, min(xx) - 8), min(width, max(xx) + 9)
            disk[y0:y1, x0:x1] = True
            disks.append(disk)
        if not disks:
            return
        boxes = np.zeros_like(bright)
        for disk in disks:
            boxes |= disk
        # Gold, including the dark outline. Gray stone and blue water stay.
        goldish = boxes & (blue < 100) & (red > blue + 20) & (red > 40) & (red + 30 > green)
        for _ in range(2):
            goldish = boxes & _dilate(goldish)
        for cy, cx in zip(*np.where(goldish)):
            for shift in range(1, 18):
                for ny, nx in ((cy, cx - shift), (cy - shift, cx), (cy, cx + shift), (cy + shift, cx)):
                    if not (0 <= ny < height and 0 <= nx < width) or goldish[ny, nx]:
                        continue
                    donor = rgb[ny, nx]
                    if int(donor[1]) < 25 and int(donor[2]) > 120:
                        continue
                    rgb[cy, cx] = donor
                    break
                else:
                    continue
                break
        # Ring fill can leave a dark speck where a circle sat on the pool.
        lum = rgb.astype(np.int16).sum(axis=2)
        water = (rgb[:, :, 2].astype(np.int16) > rgb[:, :, 0].astype(np.int16) + 20) & (rgb[:, :, 2] > 130)
        specks = (lum < 100) & _dilate(water) & _dilate(water)  # touch water
        specks &= ~water
        seen = np.zeros_like(specks)
        for y, x in zip(*np.where(specks)):
            if seen[y, x]:
                continue
            stack = [(int(y), int(x))]
            seen[y, x] = True
            pixels = []
            while stack:
                cy, cx = stack.pop()
                pixels.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and specks[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(pixels) > 500:
                continue
            for cy, cx in pixels:
                for shift in range(1, 12):
                    for ny, nx in ((cy, cx - shift), (cy + shift, cx), (cy, cx + shift), (cy - shift, cx)):
                        if 0 <= ny < height and 0 <= nx < width and water[ny, nx]:
                            rgb[cy, cx] = rgb[ny, nx]
                            break
                    else:
                        continue
                    break
        return

    # Other frames keep coin piles. Only tiny floating circles are removed.
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    gold = (red > 190) & (green > 150) & (blue < 100) & (green > blue + 40)
    height, width = gold.shape
    seen = np.zeros_like(gold)
    ys, xs = np.where(gold)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if seen[y, x]:
            continue
        stack = [(y, x)]
        seen[y, x] = True
        pixels = []
        while stack:
            cy, cx = stack.pop()
            pixels.append((cy, cx))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < height and 0 <= nx < width and gold[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if not 25 <= len(pixels) <= 420:
            continue
        for cy, cx in pixels:
            for shift in (6, 12, 20):
                for ny, nx in ((cy, cx + shift), (cy, cx - shift), (cy + shift, cx), (cy - shift, cx)):
                    if 0 <= ny < height and 0 <= nx < width and not gold[ny, nx]:
                        rgb[cy, cx] = rgb[ny, nx]
                        break
                else:
                    continue
                break


def _grow_organic(hole: np.ndarray) -> np.ndarray:
    """Widen a narrow opening along its own edge. The title, footer, and Buddy stay."""
    height, width = hole.shape
    ys, xs = np.where(hole)
    if len(xs) == 0:
        return hole
    mid = (ys > height * 0.35) & (ys < height * 0.65)
    use = mid if mid.any() else np.ones(len(xs), dtype=bool)
    span = int(np.percentile(xs[use], 98) - np.percentile(xs[use], 2))
    want = int(width * 0.62)
    if span >= want - 6:
        return hole
    grown = hole.copy()
    for _ in range(min(70, (want - span) // 2)):
        nxt = _dilate(grown)
        nxt[:68, :] = hole[:68, :]
        nxt[height - 88:, :] = hole[height - 88:, :]
        nxt[:, int(width * 0.80):] = hole[:, int(width * 0.80):]
        grown = nxt
    return grown


def _inpaint_pink(rgb: np.ndarray, hole: np.ndarray) -> None:
    """Replace leftover key-color pixels in the scenery with a nearby real pixel."""
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    pink = ((red > 185) & (green < 90) & (blue > 90) & (red > green + 80)) & ~hole
    if not pink.any():
        return
    height, width = hole.shape
    ys, xs = np.mgrid[0:height, 0:width]
    for shift in (6, 14, 26, 42, 70):
        for dy, dx in ((0, shift), (0, -shift), (shift, 0), (-shift, 0), (shift, shift), (shift, -shift)):
            src_y = np.clip(ys + dy, 0, height - 1)
            src_x = np.clip(xs + dx, 0, width - 1)
            donor = rgb[src_y, src_x]
            donor_pink = (donor[:, :, 0] > 185) & (donor[:, :, 1] < 90) & (donor[:, :, 0] > donor[:, :, 1] + 80)
            take = pink & ~donor_pink & ~hole[src_y, src_x]
            rgb[take] = donor[take]
            pink[take] = False
            if not pink.any():
                return


def _text_size(text: str, scale: int) -> tuple[int, int]:
    width = 0
    for char in text:
        glyph = _FONT[char]
        width += (len(glyph[0]) + 1) * scale
    return max(0, width - scale), 7 * scale


def _draw_text(image: Image.Image, text: str, box: tuple[int, int, int, int],
               fill: tuple[int, int, int, int], scale: int) -> None:
    pixels = image.load()
    text_w, text_h = _text_size(text, scale)
    x0, y0, bw, bh = box
    x = x0 + max(0, (bw - text_w) // 2)
    y = y0 + max(0, (bh - text_h) // 2)
    for char in text:
        glyph = _FONT[char]
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit != "1":
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        px, py = x + col * scale + sx, y + row * scale + sy
                        if 0 <= px < image.width and 0 <= py < image.height:
                            pixels[px, py] = fill
        x += (len(glyph[0]) + 1) * scale


def _boxes(mask: np.ndarray, min_n: int = 2000) -> list[tuple[int, int, int, int, int]]:
    height, width = mask.shape
    seen = np.zeros_like(mask)
    found = []
    ys, xs = np.where(mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if seen[y, x]:
            continue
        stack = [(y, x)]
        seen[y, x] = True
        minx = maxx = x
        miny = maxy = y
        count = 0
        while stack:
            cy, cx = stack.pop()
            count += 1
            minx, maxx = min(minx, cx), max(maxx, cx)
            miny, maxy = min(miny, cy), max(maxy, cy)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if count >= min_n:
            found.append((minx, miny, maxx - minx + 1, maxy - miny + 1, count))
    return found


def _distance(mask: np.ndarray, limit: int = 30) -> np.ndarray:
    """How many steps to the nearest True pixel. Pixels inside `mask` are 0."""
    dist = np.where(mask, np.int16(0), np.int16(limit + 1))
    height, width = mask.shape
    for _ in range(limit):
        padded = np.pad(dist, 1, constant_values=limit + 1)
        nearer = padded[1:-1, 1:-1]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                nearer = np.minimum(nearer, padded[1 + dy:height + 1 + dy, 1 + dx:width + 1 + dx] + 1)
        dist = nearer
    return dist


def _roughen_opening(hole: np.ndarray, well: dict[str, int]) -> np.ndarray:
    """Break a rectangular opening into an irregular rim. The portrait column stays put."""
    height, width = hole.shape
    rows = np.arange(height)[:, None]
    cols = np.arange(width)[None, :]
    field = (
        18 * np.sin(rows * 0.045)
        + 12 * np.sin(cols * 0.06 + 0.8)
        + 8 * np.sin(rows * 0.12 + cols * 0.04)
        + 6 * np.sin(rows * 0.2)
    )
    outside = _distance(hole, 32)
    inside = _distance(~hole, 32)
    expand = np.clip(field, 0, 28)
    contract = np.clip(-field, 0, 12)
    grown = hole | ((~hole) & (outside <= expand) & (outside > 0))
    bitten = grown & ~((inside > 0) & (inside <= contract))
    protect = np.zeros_like(hole)
    protect[:64, :] = True
    protect[:, max(0, well["x"] - 8):] = True
    # The controller sits on the bottom ledge. The rim may wave above it.
    protect[640:, 430:860] = True
    bitten = np.where(protect, hole, bitten)
    return bitten


def _borrow(rgb: np.ndarray, replace: np.ndarray, source: np.ndarray) -> None:
    """Spread the nearest source color into `replace`."""
    height, width = replace.shape
    known = source.copy()
    pending = replace & ~known
    ys, xs = np.mgrid[0:height, 0:width]
    for shift in range(1, 180):
        if not pending.any():
            return
        for dy, dx in ((0, -shift), (0, shift), (-shift, 0), (shift, 0)):
            src_y = np.clip(ys + dy, 0, height - 1)
            src_x = np.clip(xs + dx, 0, width - 1)
            take = pending & known[src_y, src_x]
            rgb[take] = rgb[src_y, src_x][take]
            known[take] = True
            pending[take] = False


def _remove_metal_bezel(rgb: np.ndarray, hole: np.ndarray, well: dict[str, int]) -> None:
    """The riveted border is a pre-built box. Scenery replaces it. Buddy's screen stays."""
    height, width = rgb.shape[:2]
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    foliage = (green > red + 30) & (green > blue + 15) & (green > 80)
    water = (blue > 165) & (green > 70) & (blue > green + 25) & (blue > red + 40)
    scenery = (foliage | water) & ~hole
    # Bottom bar and the empty oval. Leaves and water that already overlap it stay.
    bottom = np.zeros_like(hole)
    bottom[height - 80:, :] = True
    y0 = max(0, int(well["y"]) - 6)
    x0 = max(0, int(well["x"]) - 8)
    y1 = min(height, int(well["y"]) + int(well["height"]) + 20)
    x1 = min(width, int(well["x"]) + int(well["width"]) + 16)
    bottom[y0:y1, x0:x1] = False
    _borrow(rgb, bottom & ~scenery & ~hole, scenery)
    # Top and side rails. The centered title plaque is not steel, so it stays.
    steel = (
        (blue > 50) & (blue < 200) & (blue > red + 8)
        & (np.abs(green - red) < 40) & (green > 25) & (blue < green + 70)
    )
    rails = steel.copy()
    rails[40:height - 80, 24:width - 24] = False
    rails[y0:y1, x0:x1] = False
    _borrow(rgb, rails & ~hole, scenery)
    # Corner bracket and the tiny pad. The readable pad is drawn afterwards.
    palm = rgb[100:148, 0:150].copy()
    if palm.size:
        for y in range(0, 78):
            rgb[y, 0:150] = palm[y % palm.shape[0]]
    # The top rail is a straight bezel. Cover steel pixels and keep the title plaque.
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    steel_now = (
        (blue > 50) & (blue < 200) & (blue > red + 8)
        & (np.abs(green - red) < 40) & (green > 25) & (blue < green + 70)
    )
    top = np.zeros_like(hole)
    top[:26, :] = True
    top[:, 450:830] = False
    cover = top & steel_now
    ys, xs = np.mgrid[0:height, 0:width]
    src_y = np.clip(ys + 28, 0, height - 1)
    usable = cover & ~steel_now[src_y, xs] & ~hole[src_y, xs]
    rgb[usable] = rgb[src_y, xs][usable]
    rest = cover & ~usable
    rgb[rest & (xs < 500)] = (24, 90, 28)
    rgb[rest & (xs >= 500)] = (8, 18, 58)
    # Bottom bar: tile a real clump of leaves across whatever is not already jungle or water.
    if height > 140:
        clump = rgb[250:290, 28:108].copy()
        pink = (clump[:, :, 0] > 170) & (clump[:, :, 2] > 70) & (clump[:, :, 1] < 130)
        clump[pink] = (36, 108, 28)
        if clump.size:
            zone = np.zeros_like(hole)
            zone[height - 72:, :] = True
            zone[y0:y1, x0:x1] = False
            zone &= ~foliage & ~water & ~hole
            cy, cx = np.where(zone)
            rgb[cy, cx] = clump[cy % clump.shape[0], cx % clump.shape[1]]


def _erase_lower_plate(rgb: np.ndarray, well: dict[str, int]) -> None:
    """The empty second frame under Buddy is not part of the portrait. The ledge shows instead."""
    height, width = rgb.shape[:2]
    y0 = int(well["y"]) + int(well["height"]) + 26
    y1 = height
    x0 = max(0, int(well["x"]) - 20)
    x1 = min(width, int(well["x"]) + int(well["width"]) + 22)
    src_x1 = max(0, int(well["x"]) - 40)
    src_x0 = max(0, src_x1 - 64)
    if y0 >= y1 or src_x0 >= x0:
        return
    patch = rgb[y0:y1, src_x0:src_x1].copy()
    span = patch.shape[1]
    for index, x in enumerate(range(x0, x1)):
        rgb[y0:y1, x] = patch[:, index % span]
    # Ornaments that hang below the portrait are not scenery.
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    trim = np.zeros(rgb.shape[:2], dtype=bool)
    y_trim = min(height - 1, y0 + 18)
    block_r = red[y_trim:, x0:x1]
    block_g = green[y_trim:, x0:x1]
    block_b = blue[y_trim:, x0:x1]
    trim[y_trim:, x0:x1] = ((block_r > 140) & (block_g > 80) & (block_r > block_b + 15)) | (
        (block_b > block_r) & (block_b > 50) & (block_g < 110) & (block_r < 170)
    )
    if trim.any():
        donor_x = src_x0 + 8
        ys, xs = np.where(trim)
        rgb[ys, xs] = rgb[ys, np.full(len(ys), donor_x)]


def _cover_genesis_corner(rgb: np.ndarray, hole: np.ndarray) -> None:
    """Jungle covers the hard notch beside the pad. The review box is a 1024-wide view."""
    height, width = hole.shape
    scale = width / 1024
    x0 = int(round(75 * scale))
    x1 = int(round(130 * scale)) + 6
    y0 = int(round(20 * scale))
    y1 = int(round(130 * scale)) + 6
    leaf = rgb[220:268, 20:84]
    if leaf.size == 0:
        return
    rows = np.arange(height)
    extra = (8 + 6 * np.sin(rows * 0.15 + 0.4)).astype(int)
    for y in range(max(0, y0), min(height, y1)):
        right = min(width, x1 + int(extra[y]))
        span = hole[y, x0:right]
        if not span.any():
            continue
        sample = leaf[y % leaf.shape[0]]
        colors = np.resize(sample, (right - x0, 3))
        row = rgb[y, x0:right]
        row[span] = colors[span]
        rgb[y, x0:right] = row
        hole[y, x0:right] = False


def _draw_pad(image: Image.Image) -> None:
    """A small original three-button pad, sitting on the scenery."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    x, y, w, h = 28, 86, 108, 48
    body = (28, 32, 40, 255)
    edge = (168, 176, 188, 255)
    draw.rounded_rectangle((x, y, x + w, y + h), 8, fill=body, outline=edge, width=2)
    # Direction cross.
    cx, cy = x + 28, y + h // 2
    draw.rectangle((cx - 4, cy - 14, cx + 4, cy + 14), fill=edge)
    draw.rectangle((cx - 14, cy - 4, cx + 14, cy + 4), fill=edge)
    for index, color in enumerate(((232, 214, 170, 255), (196, 64, 72, 255), (64, 112, 196, 255))):
        bx = x + w - 58 + index * 16
        draw.ellipse((bx, y + 14, bx + 12, y + 26), fill=color)


def _black_well(rgb: np.ndarray) -> dict[str, int]:
    """The empty portrait screen: a solid near-black rectangle in the lower right."""
    lum = rgb.max(axis=2)
    dark = lum <= 14
    dark[:, :960] = False
    dark[:400, :] = False
    best = None
    for x, y, w, h, count in _boxes(dark):
        if w < 80 or h < 50:
            continue
        solidity = count / max(1, w * h)
        if solidity < 0.72:
            continue
        if best is None or count > best[-1]:
            best = (x, y, w, h, count)
    if best is None:
        return {"x": 1040, "y": 540, "width": 180, "height": 100}
    x, y, w, h, _count = best
    # Inset one pixel so the live head does not cover the frame.
    return {"x": x + 2, "y": y + 2, "width": max(40, w - 4), "height": max(40, h - 4)}


def build_plate(frame_id: str) -> tuple[Image.Image, dict[str, dict[str, int]]]:
    source = Image.open(AUTHORED / f"{frame_id}-source.jpg").convert("RGB")
    rgb = np.array(source)
    _clear_floating_rings(rgb, frame_id)
    hole = _grow_organic(_magenta_hole(rgb))
    _inpaint_pink(rgb, hole)
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    gold = (red > 180) & (green > 140) & (blue < 110) & (red + green > blue * 3)
    touching = hole
    for _ in range(3):
        touching = _dilate(touching)
    # Rings float in the opening. Coins on the stone ledge are farther out.
    hole = hole | (gold & touching)
    well = _black_well(rgb)
    if frame_id == "snes":
        hole = _roughen_opening(hole, well)
    # The click-through window is a rectangle. Keep it off Buddy's column.
    limit_x = max(0, well["x"] - 4)
    hole[:, limit_x:] = False
    _inpaint_pink(rgb, hole)
    height, width = hole.shape
    if frame_id == "genesis":
        # Pale key-color left behind in Buddy's column. The city is to the right of it.
        red = rgb[:, :, 0].astype(np.int16)
        green = rgb[:, :, 1].astype(np.int16)
        blue = rgb[:, :, 2].astype(np.int16)
        fringe = np.zeros_like(hole)
        fringe[:, limit_x:] = True
        fringe &= (
            (red > 160) & (blue > 110) & (red + 25 > blue) & (blue + 40 > red)
            & (green + 40 < red) & (green + 30 < blue)
        )
        ys, xs = np.mgrid[0:height, 0:width]
        for shift in (16, 36, 64, 96):
            if not fringe.any():
                break
            src_y = np.clip(ys, 0, height - 1)
            src_x = np.clip(xs + shift, 0, width - 1)
            donor = rgb[src_y, src_x]
            donor_red = donor[:, :, 0].astype(np.int16)
            donor_green = donor[:, :, 1].astype(np.int16)
            donor_blue = donor[:, :, 2].astype(np.int16)
            donor_fringe = (donor_red > 160) & (donor_blue > 110) & (donor_green + 40 < donor_red)
            take = fringe & ~donor_fringe
            rgb[take] = donor[take]
            fringe[take] = False
    # Slide the scenery a few pixels into the opening so the cut is not a straight wall.
    rows = np.arange(height)
    reach = (8 + 7 * np.sin(rows * 0.07) + 4 * np.sin(rows * 0.19 + 1.2)).astype(np.int16)
    for y, depth in enumerate(reach.tolist()):
        depth = int(depth)
        if depth < 2 or limit_x < 2 or not hole[y, limit_x - 1]:
            continue
        x0 = limit_x - depth
        if x0 < 0 or limit_x + depth > width:
            continue
        hole[y, x0:limit_x] = False
        rgb[y, x0:limit_x] = rgb[y, limit_x:limit_x + depth]
    if frame_id == "genesis":
        _remove_metal_bezel(rgb, hole, well)
        _cover_genesis_corner(rgb, hole)
    if frame_id == "snes":
        _erase_lower_plate(rgb, well)
    alpha = np.full(hole.shape, 255, np.uint8)
    alpha[hole] = 0
    array = np.dstack([rgb, alpha])
    image = Image.fromarray(array, "RGBA").copy()
    plaque = PLAQUES[frame_id]
    # Two lines when the plaque is tall enough. Genesis is wide and short, so
    # the title and the bit-label share one line.
    title = "BUDDY OVERLAY"
    subtitle = SUBTITLE[frame_id]
    ink = INK[frame_id]
    title_scale = 2 if _text_size(title, 2)[0] <= plaque[2] - 8 else 1
    if plaque[2] >= 340:
        _draw_text(image, f"{title}   {subtitle}", plaque, ink, title_scale)
    else:
        top = (plaque[0], plaque[1], plaque[2], max(8, plaque[3] // 2))
        bottom = (plaque[0], plaque[1] + plaque[3] // 2, plaque[2], plaque[3] - plaque[3] // 2)
        sub_scale = 2 if _text_size(subtitle, 2)[1] <= bottom[3] else 1
        _draw_text(image, title, top, ink, title_scale)
        _draw_text(image, subtitle, bottom, ink, sub_scale)
    # A tall menu sits above the portrait, in Buddy's column. Nothing is painted under the frame.
    menu_h = 100
    menu = {
        "x": well["x"],
        "y": max(48, well["y"] - menu_h - 4),
        "width": well["width"],
        "height": menu_h,
    }
    if frame_id == "genesis":
        _draw_pad(image)
    _draw_text(image, "BUDDY", (well["x"], max(0, well["y"] - 16), well["width"], 14), ink, 1)
    # Integer scale keeps the pixels crisp at 1440p. 1080p is a clean downscale.
    image = image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST)
    scale = 2
    return image, {
        "buddy": {key: int(value * scale) for key, value in well.items()},
        "menu": {key: int(value * scale) for key, value in menu.items()},
    }


def write_frames() -> dict[str, dict[str, dict[str, int]]]:
    placements = {}
    for frame_id, path in OUTPUT.items():
        image, places = build_plate(frame_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        placements[frame_id] = places
        print(path, image.size, places)
    return placements


if __name__ == "__main__":
    write_frames()
