"""Draw the overlay frame at a monitor size. No Tk, no screen capture.

The 1280x720 art scales uniformly. 1920x1080 is the 1.5x metadata. A monitor
that is not 16:9 letterboxes the frame. 'Load a game' is drawn in Buddy's
box, never in the game hole.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .capture_safety import fit_frame
from .frame_library import DESIGN, PLACEMENTS, clear_painted_head, frame_record, paste_head, punch_screen
from .hologram import render_hologram

_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _frame_art(frame_id: str) -> Image.Image:
    record = frame_record(frame_id)
    source = Image.open(Path(__file__).resolve().parents[1] / "assets" / "frames" / record["file"])
    # The baked portrait is gone before the live sprite is drawn.
    source = clear_painted_head(source, frame_id)
    return punch_screen(source, record["screen"], frame_id=frame_id)


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
    fraction = 0.28 if reserve_button else 0.18
    caption_h = 0 if game_running else max(18, int(buddy["height"] * fraction))
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


def static_frame(frame_id: str, monitor: tuple[int, int], *, game_running: bool,
                 notice: str = "") -> Image.Image:
    """Frame art only. The live head is drawn later, inside the buddy well."""
    from .retroarch_finder import NOTICE_FAILED, NOTICE_MISSING
    show_button = notice in {NOTICE_MISSING, NOTICE_FAILED}
    origin_x, origin_y, frame_w, frame_h = fit_frame(monitor)
    art = _frame_art(frame_id)
    if not game_running:
        art = _fill_hole(art)
    art = art.resize((frame_w, frame_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (int(monitor[0]), int(monitor[1])), (0, 0, 0, 255))
    import numpy as np
    array = np.array(canvas)
    array[origin_y:origin_y + frame_h, origin_x:origin_x + frame_w] = np.array(art)
    canvas = Image.fromarray(array, "RGBA")
    # Cover the baked portrait so the live head and the prompt do not stack on it.
    boxes = layout_boxes(frame_id, monitor, game_running=game_running, reserve_button=show_button)
    buddy = boxes["buddy"]
    cleared = Image.new("RGBA", (buddy["width"], buddy["height"]), (0, 0, 0, 255))
    canvas.paste(cleared, (buddy["x"], buddy["y"]))
    if not game_running:
        if show_button:
            slot = band_slots(boxes)["text"]
            _caption(canvas, slot, notice, slot["height"])
        else:
            band = boxes["buddy"]["height"] - boxes["head"]["height"]
            _caption(canvas, boxes["buddy"], notice or "Load a game", band)
    return canvas


def compose_overlay(frame_id: str, monitor: tuple[int, int], *, expression: str = "idle",
                    mouth: float = 0.0, t: float = 0.4, game_running: bool = False,
                    character: str = "male", resting: str = "left") -> Image.Image:
    """Full monitor image. The game hole is dark until a game is running."""
    canvas = static_frame(frame_id, monitor, game_running=game_running)
    head_box = layout_boxes(frame_id, monitor, game_running=game_running)["head"]
    head = render_hologram(
        expression, t=t, mouth=mouth, size=max(head_box["width"], head_box["height"]),
        character=character, resting=resting,
    )
    return paste_head(canvas, head, head_box)
