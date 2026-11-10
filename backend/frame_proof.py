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
        red = region[:, :, 0].astype(np.int16)
        green = region[:, :, 1].astype(np.int16)
        blue = region[:, :, 2].astype(np.int16)
        # Windows wallpaper is a pale blue. The game is pure blue. The art is not pale.
        wallpaper = (blue > 150) & (green > 130) & (red > 90) & (red < 210) & (blue >= red) & (np.abs(blue - green) < 60)
        if float(wallpaper.mean()) > 0.04:
            problems.append(f"the desktop is showing along the {name} of the game opening")
    return problems


def _menubar(shot: np.ndarray, game: tuple[int, int, int, int]) -> list[str]:
    """A light File / Command / Window strip means the window chrome is still there."""
    x, y, w, h = game
    bar = shot[y:y + 18, x + w // 2:x + w - 8]
    if bar.size == 0:
        return []
    if float(bar.mean()) > 150:
        return ["RetroArch's menu bar is visible on the game"]
    return []


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


def prove_snes_screen(screenshot: Image.Image, *, menu_open: bool, frame_path: Path | None = None,
                      expect_chrome: bool = True, menu_scrolled: bool = False) -> list[str]:
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
    problems.extend(_menubar(shot, game))
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
        if icon.size:
            luma = icon.astype(np.int16).max(axis=2)
            if float(luma.mean()) > 90 or int((luma > 200).sum()) < 8:
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
