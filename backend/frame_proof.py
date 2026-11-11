"""Pixel checks for the live Super NES overlay.

A dark console or a bare RetroArch window does not match Chris's painting.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .capture_safety import fit_frame
from .config_loader import ROOT
from .frame_library import DESIGN, frame_record


def _scale_box(box: dict[str, int], origin: tuple[int, int], frame: tuple[int, int]) -> tuple[int, int, int, int]:
    sx = frame[0] / DESIGN["width"]
    sy = frame[1] / DESIGN["height"]
    return (
        int(origin[0] + round(box["x"] * sx)),
        int(origin[1] + round(box["y"] * sy)),
        max(1, int(round(box["width"] * sx))),
        max(1, int(round(box["height"] * sy))),
    )


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape or a.size == 0:
        return 999.0
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def _crop(image: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    height, width = image.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    return image[y0:y1, x0:x1]


def _opening_ring(shot: np.ndarray, game: tuple[int, int, int, int]) -> list[str]:
    """The margin around the game window has to be black, never the desktop."""
    x, y, w, h = game
    height, width = shot.shape[:2]
    samples = {
        "top": shot[max(0, y - 14):max(0, y - 3), x + w // 5:x + (4 * w) // 5],
        "right": shot[y + h // 5:y + (4 * h) // 5, min(width, x + w + 3):min(width, x + w + 14)],
    }
    problems = []
    for name, region in samples.items():
        if region.size == 0:
            continue
        wallpaper = _wallpaper_mask(region)
        if float(wallpaper.mean()) > 0.04:
            problems.append(f"the desktop is showing along the {name} of the game opening")
    return problems


def _wallpaper_mask(region: np.ndarray) -> np.ndarray:
    red = region[:, :, 0].astype(np.int16)
    green = region[:, :, 1].astype(np.int16)
    blue = region[:, :, 2].astype(np.int16)
    return (blue > 150) & (green > 130) & (red > 90) & (red < 210) & (blue >= red) & (np.abs(blue - green) < 60)


def _menubar(shot: np.ndarray, game: tuple[int, int, int, int]) -> list[str]:
    """A light File / Command / Window strip means the window chrome is still there."""
    x, y, w, _h = game
    bar = shot[y:y + 36, x + w // 2:x + w - 8]
    if bar.size == 0:
        return []
    if float(bar.mean()) > 165:
        return ["RetroArch's menu bar is visible on the game"]
    return []


def _opening_interior(shot: np.ndarray, game: tuple[int, int, int, int]) -> list[str]:
    """Wallpaper inside the opening, where a too-small window would leave a gap."""
    x, y, w, h = game
    samples = {
        "right": shot[y + h // 5:y + (4 * h) // 5, x + w - 28:x + w - 4],
        "bottom": shot[y + h - 24:y + h - 4, x + w // 3:x + (2 * w) // 3],
    }
    problems = []
    for name, region in samples.items():
        if region.size == 0:
            continue
        if float(_wallpaper_mask(region).mean()) > 0.08:
            problems.append(f"the desktop is showing inside the {name} of the game opening")
    return problems


def _menu_bottom(shot: np.ndarray, button: tuple[int, int, int, int], height: int, width: int) -> list[str]:
    """Exit to desktop is a bright button at the bottom of the scrolled menu."""
    top = button[1] + button[3] + 12
    panel_h = max(240, min(height - top - 24, 920))
    panel_w = min(760, max(420, button[2] * 4))
    strip = _crop(shot, (button[0] + 16, top + panel_h - 88, min(panel_w - 32, width), 64))
    if strip.size == 0:
        return ["the bottom of the menu is off the screen"]
    red = strip[:, :, 0].astype(np.int16)
    green = strip[:, :, 1].astype(np.int16)
    blue = strip[:, :, 2].astype(np.int16)
    cyan = (blue > 180) & (green > 160) & (red < 180) & (green > red + 40)
    if int(cyan.sum()) < 30:
        return ["the menu is not scrolled to Exit to desktop"]
    return []


def _edge_strip(region: np.ndarray, side: str) -> np.ndarray:
    height, width = region.shape[:2]
    if side == "left":
        return region[height // 3: 2 * height // 3, 2:12]
    if side == "right":
        return region[height // 3: 2 * height // 3, max(0, width - 12):width - 2]
    if side == "top":
        return region[2:12, width // 3: 2 * width // 3]
    return region[max(0, height - 12):height - 2, width // 3: 2 * width // 3]


def _content_span(shot: np.ndarray, game: tuple[int, int, int, int]) -> list[str]:
    """The colored picture must fill the opening on its long side. A 3x core does not.

    A thin rim is ignored because the painted frame overlaps the rectangle's corners.
    """
    x, y, w, h = game
    inset = 4
    region = _crop(shot, (x + inset, y + inset, max(1, w - 2 * inset), max(1, h - 2 * inset)))
    if region.size == 0:
        return ["the game opening is off the screen"]
    height, width = region.shape[:2]
    bright = region.max(axis=2) > 28
    cy, cx = height // 2, width // 2
    if not bool(bright[cy, cx]):
        return ["the game picture is missing from the opening"]
    top_row = cy
    while top_row > 0 and bool(bright[top_row - 1, cx]):
        top_row -= 1
    bottom_row = cy
    while bottom_row < height - 1 and bool(bright[bottom_row + 1, cx]):
        bottom_row += 1
    left_col = cx
    while left_col > 0 and bool(bright[cy, left_col - 1]):
        left_col -= 1
    right_col = cx
    while right_col < width - 1 and bool(bright[cy, right_col + 1]):
        right_col += 1
    span_h = float(bottom_row - top_row + 1) / height
    span_w = float(right_col - left_col + 1) / width
    # Walk stops at the black gap, so frame art past the letterbox is ignored.
    # A wide opening keeps side gaps. The picture still has to meet the top and bottom.
    if top_row > max(8, int(height * 0.03)):
        return ["the game does not reach the top edge of the opening"]
    if (height - 1 - bottom_row) > max(8, int(height * 0.03)):
        return ["the game does not reach the bottom edge of the opening"]
    if span_h < 0.94:
        return [f"the game only fills {span_h:.0%} of the opening height"]
    picture_h = bottom_row - top_row + 1
    picture_w = right_col - left_col + 1
    if picture_h < 8 or picture_w < 8:
        return ["the game picture is missing from the opening"]
    aspect = picture_w / picture_h
    # A 5% tuck makes the visible slice a little wider than 4:3. A stretched
    # or fully covered opening is much wider than that.
    if aspect < 1.20 or aspect > 1.58:
        return [f"the picture aspect is {aspect:.2f}, not 4:3"]
    if max(span_w, span_h) < 0.70:
        return [
            f"the game only fills {span_w:.0%} of the opening width and {span_h:.0%} of its height"
        ]
    return []


def prove_snes_screen(screenshot: Image.Image, *, menu_open: bool, frame_path: Path | None = None,
                      expect_chrome: bool = True, menu_scrolled: bool = False,
                      expect_game: bool = False) -> list[str]:
    """Empty list means the painting, Buddy, and the hamburger are actually on screen."""
    problems: list[str] = []
    shot = np.asarray(screenshot.convert("RGB"))
    height, width = shot.shape[:2]
    if width < 1200 or height < 700:
        problems.append(f"display is {width}x{height}, wanted about 1920x1080")
    origin_x, origin_y, frame_w, frame_h = fit_frame((width, height))
    art_path = frame_path or (ROOT / "assets" / "frames" / "snes-sky-kingdom.png")
    art = Image.open(art_path).convert("RGB").resize((frame_w, frame_h), Image.Resampling.LANCZOS)
    painted = np.zeros_like(shot)
    painted[origin_y:origin_y + frame_h, origin_x:origin_x + frame_w] = np.asarray(art)
    # Right-hand scenery. The menu panel sits on the left, so these stay visible.
    for name, box in (
        ("top-right art", (2140, 40, 280, 120)),
        ("right scenery", (2060, 360, 180, 140)),
    ):
        screen_box = _scale_box(
            {"x": box[0], "y": box[1], "width": box[2], "height": box[3]},
            (origin_x, origin_y), (frame_w, frame_h),
        )
        score = _mae(_crop(shot, screen_box), _crop(painted, screen_box))
        if score > 42:
            problems.append(f"{name} does not match Chris's frame (difference {score:.0f})")
    record = frame_record("snes")
    game = _scale_box(record["screen"], (origin_x, origin_y), (frame_w, frame_h))
    problems.extend(_opening_ring(shot, game))
    problems.extend(_opening_interior(shot, game))
    problems.extend(_menubar(shot, game))
    if expect_game:
        problems.extend(_content_span(shot, game))
    buddy = _scale_box(record["buddy"], (origin_x, origin_y), (frame_w, frame_h))
    inset_x = buddy[0] + buddy[2] // 6
    inset_y = buddy[1] + buddy[3] // 6
    inset = (inset_x, inset_y, max(1, buddy[2] * 2 // 3), max(1, buddy[3] * 2 // 3))
    well = _crop(shot, inset)
    if well.size:
        red, green, blue = well[:, :, 0].astype(np.int16), well[:, :, 1].astype(np.int16), well[:, :, 2].astype(np.int16)
        glow = (blue > 70) & (blue > red + 15) & (green > 25)
        if int(glow.sum()) < 40:
            problems.append("Buddy is not drawn in the BUDDY box")
    button = _scale_box(
        {"x": 36, "y": 24, "width": 220, "height": 132},
        (origin_x, origin_y), (frame_w, frame_h),
    )
    if expect_chrome:
        icon = _crop(shot, button)
        painted_icon = _crop(painted, button)
        if icon.size:
            std = float(icon.std())
            mean = float(icon.mean())
            # A flat navy or black plate has almost no texture. The skyline does.
            if std < 22 or mean < 48:
                problems.append("the hamburger button is a flat dark fill")
            elif _mae(icon, painted_icon) > 48:
                problems.append("the hamburger button does not show the frame art")
            else:
                height, width = icon.shape[:2]
                mid = icon[:, int(width * 0.35):int(width * 0.65)].astype(np.int16)
                luma = mid.max(axis=2).mean(axis=1)
                sat = (mid.max(axis=2) - mid.min(axis=2)).mean(axis=1)
                hot = (luma > 230) & (sat > 140)
                runs = 0
                run = 0
                for flag in hot:
                    if flag:
                        run += 1
                    else:
                        if run >= 3:
                            runs += 1
                        run = 0
                if run >= 3:
                    runs += 1
                if runs < 3:
                    problems.append("the hamburger button is not visible in the top-left")
    if menu_scrolled and expect_chrome:
        problems.extend(_menu_bottom(shot, button, height, width))
    if menu_open and expect_chrome and not menu_scrolled:
        panel = (
            button[0] + 8,
            button[1] + button[3] + 28,
            min(420, width - button[0] - 16),
            80,
        )
        body = _crop(shot, panel)
        if body.size == 0 or float(body.mean()) > 70:
            problems.append("the menu panel is not open")
        else:
            blue = body[:, :, 2].astype(np.int16)
            red = body[:, :, 0].astype(np.int16)
            if int(((blue > 140) & (blue > red + 30)).sum()) < 8:
                problems.append("the menu panel has no readable text")
    return problems
