"""Rendered frames and the hologram. These do not need Windows."""
from __future__ import annotations

from backend.frames import render_frame
from backend.hologram import EXPRESSIONS, render_hologram
from backend.layout_spec import BUDDY_BOX, HOLE, MENU_BUTTON, overlaps

FORBIDDEN = ("sega", "nintendo", "sonic", "mario", "zion", "famicom")


def _alpha(image, x, y):
    return image.getpixel((x, y))[3]


def test_layout_rects_do_not_cover_each_other():
    assert not overlaps(HOLE, BUDDY_BOX)
    assert not overlaps(HOLE, MENU_BUTTON)
    assert not overlaps(BUDDY_BOX, MENU_BUTTON)


def test_frames_have_a_transparent_opening_and_no_trademarks():
    for theme in ("nes", "snes", "genesis"):
        art = render_frame(theme, "GAME WINGMAN")
        image = art.image
        assert image.size == (1920, 1080)
        assert image.mode == "RGBA"
        hx, hy, hw, hh = HOLE
        assert _alpha(image, hx + hw // 2, hy + hh // 2) == 0
        assert _alpha(image, hx + 2, hy + 2) == 0
        assert _alpha(image, 8, 8) == 255
        mx, my, mw, mh = MENU_BUTTON
        assert _alpha(image, mx + mw // 2, my + mh // 2) == 255
        blob = " ".join(art.labels).lower()
        for word in FORBIDDEN:
            assert word not in blob
        assert "BUDDY" in art.labels
        assert "GAME WINGMAN" in art.labels


def test_hologram_expressions_are_distinct_and_stable():
    idle = render_hologram("idle", t=0.2, mouth=0.0, size=128)
    again = render_hologram("idle", t=0.2, mouth=0.0, size=128)
    assert idle.tobytes() == again.tobytes()
    for name in EXPRESSIONS:
        mouth = 0.8 if name in {"talk", "laugh", "shocked"} else 0.0
        image = render_hologram(name, t=0.2, mouth=mouth, size=128)
        assert image.mode == "RGBA"
        assert image.getbbox() is not None
        if name != "idle":
            assert image.tobytes() != idle.tobytes()
