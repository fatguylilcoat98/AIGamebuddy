"""Shared overlay geometry in 1920x1080 pixels.

Rects are (x, y, width, height). The game hole is the only fully transparent
region. Every theme uses this same layout so the emulator can sit in one place.
"""
from __future__ import annotations

OUTPUT_W = 1920
OUTPUT_H = 1080

# Multiples of 12 so NES (6px), SNES/Genesis (4px) blocks stay aligned.
HOLE = (288, 144, 1152, 792)
BUDDY_BOX = (1488, 588, 396, 456)
BUDDY_SCREEN = (1512, 684, 348, 312)
MENU_BUTTON = (1752, 24, 132, 72)
CAPTION = (288, 948, 1152, 96)

THEMES = ("nes", "snes", "genesis")

THEME_META = {
    "nes": {
        "label": "8-BIT",
        "subtitle": "DUNGEON",
        "block": 6,
    },
    "snes": {
        "label": "SUPER 16-BIT",
        "subtitle": "FANTASY",
        "block": 4,
    },
    "genesis": {
        "label": "16-BIT",
        "subtitle": "SPEED",
        "block": 4,
    },
}


def rect_inside(rect: tuple[int, int, int, int], width: int = OUTPUT_W, height: int = OUTPUT_H) -> bool:
    x, y, w, h = rect
    return w > 0 and h > 0 and x >= 0 and y >= 0 and x + w <= width and y + h <= height


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def scale_rect(rect: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    return (
        round(x * width / OUTPUT_W),
        round(y * height / OUTPUT_H),
        max(1, round(w * width / OUTPUT_W)),
        max(1, round(h * height / OUTPUT_H)),
    )


def hole_for_window(width: int, height: int) -> tuple[int, int, int, int]:
    return scale_rect(HOLE, width, height)
