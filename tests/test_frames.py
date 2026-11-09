"""Rendered frames and the hologram. These do not need Windows."""
from __future__ import annotations

from backend.frames import render_frame
from backend.hologram import EXPRESSIONS, render_hologram
from backend.hologram_art import get_art, mirror_fix_gb, split_sheet
from pathlib import Path
from PIL import Image, ImageOps
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


def test_sheets_split_and_turns_keep_gb_readable():
    root = Path("assets/hologram/source")
    for name in ("male-expressions.jpg", "female-expressions.jpg", "male-turns.jpg", "female-turns.jpg"):
        panels = split_sheet(root / name)
        assert len(panels) == 8
    male = get_art("male")
    female = get_art("female")
    assert "faces left" in male.notes[0]
    assert "faces right" in female.notes[0]
    # Female's left-facing strong turn is mirrored, so GB is redrawn rather than reversed.
    source = split_sheet(root / "female-turns.jpg")[3]
    fixed = mirror_fix_gb(source)
    assert fixed.tobytes() != ImageOps.mirror(source).tobytes()
    assert male.front["neutral"].getpixel((0, 0))[3] == 0
    assert female.front["grin"].getpixel((0, 0))[3] == 0
    assert male.left_turns[-1][0] == 1.0
    assert male.right_turns[-1][0] == 1.0


def test_hologram_expressions_are_distinct_and_stable():
    idle = render_hologram("idle", t=0.2, mouth=0.0, size=96, character="male", resting="left")
    again = render_hologram("idle", t=0.2, mouth=0.0, size=96, character="male", resting="left")
    assert idle.tobytes() == again.tobytes()
    assert render_hologram("idle", t=2.4, mouth=0.0, size=96).tobytes() != idle.tobytes()
    for name in EXPRESSIONS:
        mouth = 0.9 if name in {"talk", "laugh", "shocked", "celebrate"} else 0.0
        image = render_hologram(name, t=0.2, mouth=mouth, size=96, resting="center")
        assert image.mode == "RGBA"
        assert image.getbbox() is not None
        if name != "idle":
            assert image.tobytes() != idle.tobytes()
    closed = render_hologram("talk", t=0.2, mouth=0.0, size=96, resting="center")
    opened = render_hologram("talk", t=0.2, mouth=1.0, size=96, resting="center")
    assert closed.tobytes() != opened.tobytes()
    female = render_hologram("idle", t=0.2, mouth=0.0, size=96, character="female")
    assert female.tobytes() != idle.tobytes()
    right = render_hologram("idle", t=0.2, mouth=0.0, size=96, resting="right")
    assert right.tobytes() != idle.tobytes()
