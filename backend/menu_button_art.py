"""The top-left menu control, painted in the same colors as the frame.

It is not a flat black box. The city and the sunset stay visible, and three
neon bars sit on top in the magenta, gold, and cyan already in the painting.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .chris_snes_frame import HAMBURGER


def paint_menu_button(image: Image.Image, box: dict | None = None) -> Image.Image:
    """Darken the art under the control and paint three bars over it."""
    rect = box or HAMBURGER
    out = image.convert("RGBA")
    x, y, w, h = int(rect["x"]), int(rect["y"]), int(rect["width"]), int(rect["height"])
    if w < 8 or h < 8:
        return out
    darkened = out.crop((x, y, x + w, y + h))
    pixels = darkened.load()
    for py in range(h):
        for px in range(w):
            red, green, blue, alpha = pixels[px, py]
            pixels[px, py] = (int(red * 0.78), int(green * 0.78), int(blue * 0.78), alpha)
    out.paste(darkened, (x, y))
    draw = ImageDraw.Draw(out)
    margin = max(10, min(w, h) // 8)
    draw.rounded_rectangle(
        (x + margin, y + margin, x + w - margin, y + h - margin),
        radius=max(8, margin), outline=(255, 70, 190, 255), width=max(3, margin // 5),
    )
    inset = margin + max(4, margin // 3)
    draw.rounded_rectangle(
        (x + inset, y + inset, x + w - inset, y + h - inset),
        radius=max(6, margin - 2), outline=(80, 220, 255, 220), width=max(2, margin // 8),
    )
    bar_w = w - 2 * margin - max(24, w // 7)
    bar_h = max(7, h // 12)
    gap = max(8, bar_h)
    left = x + (w - bar_w) // 2
    top = y + (h - (bar_h * 3 + gap * 2)) // 2
    colors = ((255, 64, 186, 255), (255, 210, 48, 255), (64, 230, 255, 255))
    for index, color in enumerate(colors):
        by = top + index * (bar_h + gap)
        draw.rounded_rectangle(
            (left - 3, by - 3, left + bar_w + 3, by + bar_h + 3),
            radius=6, fill=(36, 8, 52, 255),
        )
        draw.rounded_rectangle((left, by, left + bar_w, by + bar_h), radius=5, fill=color)
        core_top = by + max(2, bar_h // 3)
        draw.rounded_rectangle(
            (left + 10, core_top, left + bar_w - 10, core_top + max(2, bar_h // 5)),
            radius=2, fill=(255, 250, 240, 230),
        )
    return out


def button_face(art: Image.Image, origin: tuple[int, int], frame_size: tuple[int, int],
                box: dict[str, int]) -> Image.Image:
    """The painted control at the overlay's current size, for the clickable button."""
    scaled = art.convert("RGBA").resize(frame_size, Image.Resampling.LANCZOS)
    x = int(box["x"]) - int(origin[0])
    y = int(box["y"]) - int(origin[1])
    width = max(1, int(box["width"]))
    height = max(1, int(box["height"]))
    return scaled.crop((x, y, x + width, y + height)).convert("RGB")
