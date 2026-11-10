"""Three neon bars drawn on the frame's own pixels.

Nothing is filled in behind them. The sunset and the skyline stay, with a thin
outline and the bars on top.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .chris_snes_frame import HAMBURGER


def paint_menu_button(image: Image.Image, box: dict | None = None) -> Image.Image:
    """Draw the menu control onto a copy of the frame. The art under it stays."""
    rect = box or HAMBURGER
    out = image.convert("RGBA").copy()
    x, y, w, h = int(rect["x"]), int(rect["y"]), int(rect["width"]), int(rect["height"])
    if w < 8 or h < 8:
        return out
    draw = ImageDraw.Draw(out)
    margin = max(8, min(w, h) // 9)
    draw.rounded_rectangle(
        (x + margin, y + margin, x + w - margin, y + h - margin),
        radius=max(8, margin), outline=(255, 80, 200, 255), width=max(2, margin // 6),
    )
    inset = margin + max(3, margin // 4)
    draw.rounded_rectangle(
        (x + inset, y + inset, x + w - inset, y + h - inset),
        radius=max(6, margin - 2), outline=(90, 230, 255, 255), width=max(2, margin // 8),
    )
    bar_w = w - 2 * margin - max(28, w // 6)
    bar_h = max(6, h // 14)
    gap = max(8, bar_h + 2)
    left = x + (w - bar_w) // 2
    top = y + (h - (bar_h * 3 + gap * 2)) // 2
    colors = ((255, 70, 190, 255), (255, 214, 54, 255), (70, 236, 255, 255))
    for index, color in enumerate(colors):
        by = top + index * (bar_h + gap)
        draw.rounded_rectangle(
            (left - 2, by - 2, left + bar_w + 2, by + bar_h + 2),
            radius=5, outline=(255, 250, 245, 255), width=2,
        )
        draw.rounded_rectangle((left, by, left + bar_w, by + bar_h), radius=4, fill=color)
    return out
