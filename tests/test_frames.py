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


def test_head_is_centered_in_the_well():
    """The live head's box is centered in the well and does not leave it."""
    import numpy as np
    from backend.frame_library import frame_record
    from backend.overlay_view import compose_overlay

    def bounds(image, well):
        crop = np.asarray(image.convert("RGB").crop(
            (well["x"], well["y"], well["x"] + well["width"], well["y"] + well["height"])))
        red = crop[:, :, 0].astype(int)
        blue = crop[:, :, 2].astype(int)
        green = crop[:, :, 1].astype(int)
        mask = (blue > 70) & (blue > red + 25) & (green > 15)
        ys, xs = np.where(mask)
        return xs, ys

    for frame_id in ("genesis", "nes", "snes"):
        well = frame_record(frame_id)["well"]
        for character in ("male", "female"):
            for size, limit in (((1280, 720), 8), ((1920, 1080), 12)):
                image = compose_overlay(
                    frame_id, size, expression="idle", character=character, resting="left",
                )
                scale_x = size[0] / 1280
                scale_y = size[1] / 720
                box = {
                    "x": int(round(well["x"] * scale_x)),
                    "y": int(round(well["y"] * scale_y)),
                    "width": int(round(well["width"] * scale_x)),
                    "height": int(round(well["height"] * scale_y)),
                }
                xs, ys = bounds(image, box)
                assert len(xs) > 20, (frame_id, character, size)
                center = (int(xs.min()) + int(xs.max())) / 2
                assert abs(center - box["width"] / 2) <= limit, (frame_id, character, size, center)
                assert int(xs.min()) >= 2 and int(xs.max()) <= box["width"] - 3
                assert int(ys.min()) >= 6, (frame_id, character, size, int(ys.min()))
                assert int(ys.max()) <= box["height"] - 4


def test_bezel_overhangs_the_hole():
    import numpy as np
    from backend.frame_library import BEZEL_OVERHANG, FRAME_DIR, FRAME_FILES, frame_record, punch_screen
    for frame_id, filename in FRAME_FILES.items():
        image = Image.open(FRAME_DIR / filename)
        screen = frame_record(frame_id)["screen"]
        punched = np.array(punch_screen(image, screen, frame_id=frame_id))
        x, y, w, h = screen["x"], screen["y"], screen["width"], screen["height"]
        lip = BEZEL_OVERHANG
        top = punched[y:y + lip, x + lip:x + w - lip, 3]
        left = punched[y + lip:y + h - lip, x:x + lip, 3]
        assert int((top > 200).sum()) > 10, frame_id
        assert int((left > 200).sum()) > 10, frame_id
        center = punched[y + h // 2, x + w // 2, 3]
        assert int(center) == 0


def test_approved_composite_keeps_the_bezel():
    import numpy as np
    from backend.frame_library import FRAME_DIR, FRAME_FILES, PLACEMENTS, paste_head
    for frame_id, filename in FRAME_FILES.items():
        source = Image.open(FRAME_DIR / filename).convert("RGBA")
        box = PLACEMENTS[frame_id]["buddy"]
        rest = render_hologram("idle", t=0.4, mouth=0.0, size=280, character="male", resting="left")
        talk = render_hologram("talk", t=0.4, mouth=0.9, size=280, character="male", resting="left")
        src = np.asarray(source)
        mask = np.ones(src.shape[:2], dtype=bool)
        mask[box["y"]:box["y"] + box["height"], box["x"]:box["x"] + box["width"]] = False
        for head in (rest, talk):
            composed = np.asarray(paste_head(source, head, box))
            assert np.array_equal(src[mask], composed[mask])
        assert np.asarray(paste_head(source, talk, box)).tobytes() != src.tobytes()
    # The old SNES box covered this bezel pixel. It has to stay outside the well.
    snes_box = PLACEMENTS["snes"]["buddy"]
    assert snes_box["x"] + snes_box["width"] <= 1236
    assert snes_box["y"] + snes_box["height"] <= 576
    snes = Image.open(FRAME_DIR / "snes-sky-kingdom.jpg").convert("RGBA")
    talk = render_hologram("talk", t=0.4, mouth=0.9, size=280, character="male", resting="left")
    assert paste_head(snes, talk, snes_box).getpixel((1244, 360)) == snes.getpixel((1244, 360))


def test_rest_pose_faces_left_until_talking():
    from backend.hologram import _pose_sprite, yaw_at
    from backend.hologram_art import frame_rest_pose, get_art
    for t in (0.0, 0.4, 1.1, 2.2, 3.5, 5.0):
        assert yaw_at(t, "idle", "left") <= -0.8
        assert yaw_at(t, "smile", "left") <= -0.8
        assert abs(yaw_at(t, "talk", "left")) <= 0.05
    profile = frame_rest_pose()
    # Male rest is the unmirrored approved-frame cut. The brim points left.
    assert _pose_sprite("male", "idle", yaw_at(0.3, "idle", "left"), 0).tobytes() == profile.tobytes()
    assert profile.tobytes() != get_art("male").front["neutral"].tobytes()
    assert _cap_text_present(profile)
    female_rest = get_art("female").rest_left
    assert female_rest.tobytes() != get_art("female").front["neutral"].tobytes()
    assert _cap_text_present(female_rest)
    from backend.hologram_art import brim_faces_left, key_black
    from backend.frame_library import FRAME_DIR, PLACEMENTS
    from backend.overlay_view import compose_overlay, layout_boxes
    raw_box = PLACEMENTS["snes"]["buddy"]
    raw = key_black(Image.open(FRAME_DIR / "snes-sky-kingdom.jpg").convert("RGB").crop(
        (raw_box["x"], raw_box["y"], raw_box["x"] + raw_box["width"], raw_box["y"] + raw_box["height"])))
    mirrored = key_black(ImageOps.mirror(raw.convert("RGB")))
    assert brim_faces_left(raw)
    assert not brim_faces_left(mirrored)
    assert brim_faces_left(profile)
    assert profile.tobytes() == raw.tobytes()
    assert brim_faces_left(female_rest)
    assert not brim_faces_left(ImageOps.mirror(female_rest))
    for size in ((1280, 720), (1920, 1080), (2560, 1440)):
        for character in ("male", "female"):
            image = compose_overlay(
                "snes", size, expression="idle", game_running=False, character=character,
            )
            box = layout_boxes("snes", size, game_running=False)["head"]
            crop = image.crop((box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]))
            assert brim_faces_left(crop), (character, size)
    rest = render_hologram("idle", t=0.3, mouth=0.0, size=140, character="male", resting="left")
    talking = render_hologram("talk", t=0.3, mouth=0.9, size=140, character="male", resting="left")
    assert rest.tobytes() != talking.tobytes()


def _cap_text_present(image) -> bool:
    import numpy as np
    array = np.asarray(image.convert("RGBA"))
    bright = (
        (array[:, :, 3] > 180)
        & (array[:, :, 0] > 170)
        & (array[:, :, 1] > 170)
        & (array[:, :, 2] > 190)
    )
    return int(bright.sum()) > 40


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
