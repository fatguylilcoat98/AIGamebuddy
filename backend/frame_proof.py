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


def prove_snes_screen(screenshot: Image.Image, *, menu_open: bool, frame_path: Path | None = None,
                      expect_chrome: bool = True) -> list[str]:
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
    if menu_open and expect_chrome:
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
