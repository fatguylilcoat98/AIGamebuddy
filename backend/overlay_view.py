"""Draw the overlay frame at a monitor size. No Tk, no screen capture.

The 1280x720 art scales uniformly. 1920x1080 is the 1.5x metadata. A monitor
that is not 16:9 letterboxes the frame. 'Load a game' is drawn in Buddy's
box, never in the game hole.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config_loader import ROOT
from .capture_safety import fit_frame
from .frame_library import DESIGN, PLACEMENTS, clear_painted_head, frame_record, paste_head, punch_screen
from .hologram import render_hologram

_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def seal_opening(image: Image.Image, screen: dict[str, int]) -> Image.Image:
    """Keep only the game rectangle clear. The rest of the opening is opaque black.

    Transparent pixels outside that rectangle used to show the desktop.
    """
    import numpy as np
    array = np.array(image.convert("RGBA"))
    height, width = array.shape[:2]
    x = max(0, int(screen["x"]))
    y = max(0, int(screen["y"]))
    x1 = min(width, x + max(1, int(screen["width"])))
    y1 = min(height, y + max(1, int(screen["height"])))
    transparent = array[:, :, 3] < 250
    inside = np.zeros((height, width), dtype=bool)
    inside[y:y1, x:x1] = True
    array[transparent & ~inside] = (0, 0, 0, 255)
    return Image.fromarray(array, "RGBA")


def punch_wide_gutters(image: Image.Image) -> Image.Image:
    """Open the near-black gutters inside WIDE_RECT so the game shows through.

    Colorful art stays opaque. The Buddy well stays opaque. Nothing outside
    the wide picture, plus a 2-pixel tuck, is touched, so the flood cannot
    leak to the canvas edges.
    """
    import numpy as np
    from .frame_library import DESIGN, frame_record
    from .retroarch_finder import WIDE_RECT

    array = np.array(image.convert("RGBA"))
    height, width = array.shape[:2]
    design_w, design_h = int(DESIGN["width"]), int(DESIGN["height"])
    scale_x = width / design_w
    scale_y = height / design_h
    rx, ry, rw, rh = (int(v) for v in WIDE_RECT)
    pad = 2
    x0 = max(0, int(round(rx * scale_x)) - pad)
    y0 = max(0, int(round(ry * scale_y)) - pad)
    x1 = min(width, int(round((rx + rw) * scale_x)) + pad)
    y1 = min(height, int(round((ry + rh) * scale_y)) + pad)
    lum = array[:, :, :3].max(axis=2)
    hole = np.zeros((height, width), dtype=bool)
    hole[y0:y1, x0:x1] = lum[y0:y1, x0:x1] <= 36
    well = frame_record("snes").get("well") or frame_record("snes")["buddy"]
    wx = max(0, int(round(int(well["x"]) * scale_x)))
    wy = max(0, int(round(int(well["y"]) * scale_y)))
    ww = max(1, int(round(int(well["width"]) * scale_x)))
    wh = max(1, int(round(int(well["height"]) * scale_y)))
    hole[wy:wy + wh, wx:wx + ww] = False
    array[hole, 3] = 0
    return Image.fromarray(array, "RGBA")


def _frame_art(frame_id: str) -> Image.Image:
    record = frame_record(frame_id)
    source = Image.open(ROOT / "assets" / "frames" / record["file"])
    # The baked portrait is gone before the live sprite is drawn.
    source = clear_painted_head(source, frame_id)
    art = punch_screen(source, record["screen"], frame_id=frame_id)
    if frame_id == "snes":
        art = seal_opening(art, record["screen"])
        # The three bars are part of the painting. Draw them again so a black
        # plate cannot cover the skyline.
        from .menu_button_art import paint_menu_button
        art = paint_menu_button(art, record.get("menu"))
    return art


def _fill_hole(image: Image.Image, color: tuple[int, int, int, int] = (6, 8, 14, 255)) -> Image.Image:
    import numpy as np
    array = np.array(image.convert("RGBA"))
    hole = array[:, :, 3] < 16
    array[hole] = color
    return Image.fromarray(array, "RGBA")


def _box(frame_id: str, key: str, origin: tuple[int, int], frame_size: tuple[int, int]) -> dict[str, int]:
    raw = PLACEMENTS[frame_id][key]
    sx = frame_size[0] / DESIGN["width"]
    sy = frame_size[1] / DESIGN["height"]
    return {
        "x": int(round(origin[0] + raw["x"] * sx)),
        "y": int(round(origin[1] + raw["y"] * sy)),
        "width": max(1, int(round(raw["width"] * sx))),
        "height": max(1, int(round(raw["height"] * sy))),
    }


def _caption(image: Image.Image, box: dict[str, int], text: str, band: int) -> None:
    """Draw inside the bottom `band` pixels of the buddy box, never in the hole."""
    draw = ImageDraw.Draw(image)
    size = max(11, int(band * 0.55))
    try:
        font = ImageFont.truetype(_FONT, size)
    except OSError:
        font = ImageFont.load_default()
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_w = right - left
    text_h = bottom - top
    x = box["x"] + max(0, (box["width"] - text_w) // 2)
    y = box["y"] + box["height"] - band + max(0, (band - text_h) // 2)
    draw.text((x, y), text, font=font, fill=(232, 244, 255, 255))


def _well_box(frame_id: str, origin: tuple[int, int], frame_size: tuple[int, int]) -> dict[str, int]:
    """The real inner plate, not the older hand-tuned portrait rect."""
    record = frame_record(frame_id)
    raw = record.get("well") or PLACEMENTS[frame_id]["buddy"]
    sx = frame_size[0] / DESIGN["width"]
    sy = frame_size[1] / DESIGN["height"]
    return {
        "x": int(round(origin[0] + raw["x"] * sx)),
        "y": int(round(origin[1] + raw["y"] * sy)),
        "width": max(1, int(round(raw["width"] * sx))),
        "height": max(1, int(round(raw["height"] * sy))),
    }


def layout_boxes(frame_id: str, monitor: tuple[int, int], *, game_running: bool,
                 reserve_button: bool = False) -> dict:
    origin_x, origin_y, frame_w, frame_h = fit_frame(monitor)
    buddy = _well_box(frame_id, (origin_x, origin_y), (frame_w, frame_h))
    menu = _box(frame_id, "menu", (origin_x, origin_y), (frame_w, frame_h))
    # The head uses the whole well. A find-RetroArch button is the only thing that borrows the bottom.
    caption_h = 0 if (game_running or not reserve_button) else max(28, int(buddy["height"] * 0.22))
    head = {
        "x": buddy["x"],
        "y": buddy["y"],
        "width": buddy["width"],
        "height": max(8, buddy["height"] - caption_h),
    }
    return {
        "origin": (origin_x, origin_y),
        "frame": (frame_w, frame_h),
        "buddy": buddy,
        "head": head,
        "menu": menu,
    }


def band_slots(boxes: dict) -> dict[str, dict[str, int]]:
    """Text and button rectangles inside Buddy's box, under the head."""
    buddy = boxes["buddy"]
    head = boxes["head"]
    top = head["y"] + head["height"]
    height = max(0, buddy["y"] + buddy["height"] - top)
    text_h = min(height, max(12, int(height * 0.46))) if height else 0
    return {
        "text": {"x": buddy["x"], "y": top, "width": buddy["width"], "height": text_h},
        "button": {
            "x": buddy["x"] + 4,
            "y": top + text_h,
            "width": max(1, buddy["width"] - 8),
            "height": max(1, height - text_h),
        },
    }


def rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def _dilate(mask, steps: int):
    import numpy as np
    out = mask.copy()
    for _ in range(max(0, steps)):
        grown = out.copy()
        grown[1:] |= out[:-1]
        grown[:-1] |= out[1:]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def _erode(mask, steps: int):
    import numpy as np
    return ~_dilate(~mask, steps)


def _rect_mask(shape, rect):
    import numpy as np
    height, width = shape
    mask = np.zeros(shape, dtype=bool)
    x, y, w, h = rect
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(width, int(x) + int(w)), min(height, int(y) + int(h))
    if x1 > x0 and y1 > y0:
        mask[y0:y1, x0:x1] = True
    return mask


def _black_opening_mask(array, opening, keep) :
    """Every near-black pixel of the opening, plus a few pixels under the art.

    Thin dark lines in the painting are eroded away so the flood stays in the
    solid black gap and does not repaint the dragon or the hamburger.
    """
    import numpy as np
    rgb = array[:, :, :3]
    height, width = rgb.shape[:2]
    blocked = np.zeros((height, width), dtype=bool)
    for rect in keep:
        blocked |= _rect_mask((height, width), rect)
    dark = (rgb.max(axis=2) <= 10) & ~blocked
    solid = _erode(dark, 4) & ~blocked
    reach = _rect_mask((height, width), opening)
    reach = _erode(reach, 4) & ~blocked
    if not reach.any():
        reach = _rect_mask((height, width), opening) & ~blocked
    for _ in range(480):
        grown = _dilate(reach, 1)
        nxt = (grown & (solid | reach)) & ~blocked
        if np.array_equal(nxt, reach):
            break
        reach = nxt
    # Grow back across the eroded edge and a few pixels under the real art.
    covered = _dilate(reach, 4 + 6) | _rect_mask((height, width), opening)
    return covered & ~blocked


def paint_blue_opening(canvas: Image.Image, frame_id: str, monitor: tuple[int, int]) -> Image.Image:
    """Blue fills the whole black opening and tucks under the art.

    The 4:3 game hole stays clear. Colorful art, the hamburger, and Buddy's
    well stay in front of the blue.
    """
    import numpy as np
    from .display_info import hole_screen_rect
    from .retroarch_finder import visible_picture
    record = frame_record(frame_id)
    monitor_box = (0, 0, monitor[0], monitor[1])
    opening = hole_screen_rect(record["screen"], monitor_box)
    game = visible_picture(opening)
    keep = [
        hole_screen_rect(record["menu"], monitor_box),
        hole_screen_rect(record.get("well") or record["buddy"], monitor_box),
    ]
    array = np.array(canvas.convert("RGBA"))
    saved = array.copy()
    blue = _black_opening_mask(array, opening, keep)
    array[blue] = (0, 40, 220, 255)
    # The painting covers the tuck. Near-black gap pixels are not art.
    colorful = (saved[:, :, 3] > 180) & (saved[:, :, :3].max(axis=2) >= 32)
    restore = colorful & blue
    array[restore] = saved[restore]
    for rect in keep:
        hold = _rect_mask(array.shape[:2], rect)
        array[hold] = saved[hold]
    gx, gy, gw, gh = game
    game_mask = _rect_mask(array.shape[:2], (gx, gy, gw, gh))
    # Art that overlaps the picture stays opaque and in front.
    punch = game_mask & ~colorful
    array[punch, 3] = 0
    return Image.fromarray(array, "RGBA")


def art_free_hole(canvas: Image.Image, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Shrink the click-through cut so frame art at the opening's edges stays drawn.

    Rows and columns at the edge of `rect` that still hold opaque art are
    trimmed. The rest of the game shows through the transparent color.
    """
    import numpy as np
    x, y, width, height = (int(v) for v in rect)
    alpha = np.array(canvas.convert("RGBA"))[:, :, 3]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(alpha.shape[1], x + width), min(alpha.shape[0], y + height)
    if x1 <= x0 or y1 <= y0:
        return x, y, max(1, width), max(1, height)
    solid = alpha[y0:y1, x0:x1] > 0
    for _ in range(4):
        rows = solid.any(axis=1)
        cols = solid.any(axis=0)
        top = 0
        while top < len(rows) and rows[top]:
            top += 1
        bottom = len(rows)
        while bottom > top and rows[bottom - 1]:
            bottom -= 1
        left = 0
        while left < len(cols) and cols[left] and solid[top:bottom, left].any():
            left += 1
        right = len(cols)
        while right > left and solid[top:bottom, right - 1].any():
            right -= 1
        if bottom <= top or right <= left:
            return x, y, max(1, width), max(1, height)
        if (top, bottom, left, right) == (0, len(rows), 0, len(cols)):
            break
        solid = solid[top:bottom, left:right]
        x0, y0 = x0 + left, y0 + top
        x1, y1 = x0 + (right - left), y0 + (bottom - top)
    return x0, y0, x1 - x0, y1 - y0


def static_frame(frame_id: str, monitor: tuple[int, int], *, game_running: bool,
                 notice: str = "") -> Image.Image:
    """Frame art only. The live head is drawn later, inside the buddy well."""
    from .retroarch_finder import NOTICE_FAILED, NOTICE_MISSING
    show_button = notice in {NOTICE_MISSING, NOTICE_FAILED}
    origin_x, origin_y, frame_w, frame_h = fit_frame(monitor)
    art = _frame_art(frame_id)
    if not game_running:
        art = _fill_hole(art)
    elif frame_id == "snes":
        from .retroarch_finder import GAME_FIT
        if GAME_FIT == "wide":
            art = punch_wide_gutters(art)
    art = art.resize((frame_w, frame_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (int(monitor[0]), int(monitor[1])), (0, 0, 0, 255))
    import numpy as np
    array = np.array(canvas)
    array[origin_y:origin_y + frame_h, origin_x:origin_x + frame_w] = np.array(art)
    canvas = Image.fromarray(array, "RGBA")
    if game_running and frame_id == "snes":
        from .retroarch_finder import GAME_FIT
        if GAME_FIT != "wide":
            canvas = paint_blue_opening(canvas, frame_id, monitor)
    boxes = layout_boxes(frame_id, monitor, game_running=game_running, reserve_button=show_button)
    if not game_running:
        if show_button:
            slot = band_slots(boxes)["text"]
            _caption(canvas, slot, notice, slot["height"])
        else:
            _caption(canvas, boxes["menu"], notice or "", max(12, boxes["menu"]["height"] // 3))
    return canvas


def compose_overlay(frame_id: str, monitor: tuple[int, int], *, expression: str = "idle",
                    mouth: float = 0.0, t: float = 0.4, game_running: bool = False,
                    character: str = "male", resting: str = "left") -> Image.Image:
    """Full monitor image. The game hole is dark until a game is running."""
    canvas = static_frame(frame_id, monitor, game_running=game_running)
    head_box = layout_boxes(frame_id, monitor, game_running=game_running)["head"]
    yaw = 0.0 if expression == "talk" else -0.85
    head = render_hologram(
        expression, t, mouth, size=max(head_box["width"], head_box["height"]),
        character=character, resting=resting, yaw=yaw,
    )
    return paste_head(canvas, head, head_box)
