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
    from backend.frame_library import DESIGN, frame_record
    from backend.overlay_view import compose_overlay

    def bounds(image, well):
        crop = np.asarray(image.convert("RGB").crop(
            (well["x"], well["y"], well["x"] + well["width"], well["y"] + well["height"])))
        red = crop[:, :, 0].astype(int)
        blue = crop[:, :, 2].astype(int)
        green = crop[:, :, 1].astype(int)
        mask = (blue > 90) & (blue > red + 40) & (green > 30)
        rim = max(4, crop.shape[0] // 18)
        mask[:rim, :] = False
        mask[-rim:, :] = False
        mask[:, :rim] = False
        mask[:, -rim:] = False
        ys, xs = np.where(mask)
        return xs, ys

    for frame_id in ("genesis", "nes", "snes"):
        well = frame_record(frame_id)["well"]
        for character in ("male", "female"):
            for size, limit in (((1280, 720), 8), ((1920, 1080), 12)):
                image = compose_overlay(
                    frame_id, size, expression="idle", character=character, resting="left",
                )
                scale_x = size[0] / DESIGN["width"]
                scale_y = size[1] / DESIGN["height"]
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
                assert int(ys.min()) >= 2, (frame_id, character, size, int(ys.min()))
                span = int(ys.max()) - int(ys.min()) + 1
                assert 0.78 <= span / box["height"] <= 0.93, (frame_id, character, size, span, box["height"])
                assert int(ys.max()) <= box["height"] - 2


def test_scenery_nibbles_the_opening_without_a_hard_frame():
    """The opening is most of the frame. Scenery crosses the edge instead of a rectangle."""
    import numpy as np
    from backend.frame_library import FRAME_DIR, FRAME_FILES, frame_record, punch_screen
    for frame_id, filename in FRAME_FILES.items():
        image = Image.open(FRAME_DIR / filename)
        screen = frame_record(frame_id)["screen"]
        punched = np.array(punch_screen(image, screen, frame_id=frame_id))
        alpha = punched[:, :, 3]
        hole = alpha < 16
        height, width = hole.shape
        mid = hole[int(height * 0.35):int(height * 0.65)]
        span = int(mid.any(axis=0).sum()) / width
        x, y, w, h = screen["x"], screen["y"], screen["width"], screen["height"]
        region = alpha[y:y + h, x:x + w]
        assert int(region[h // 2, w // 2]) == 0
        if frame_id == "snes":
            # Chris's opening is the black center. The title and the controller stay solid.
            assert 0.50 <= span <= 0.80, (frame_id, round(span, 3))
            assert int(alpha[40, width // 2]) == 255
            assert int(alpha[height - 80, width // 2]) == 255
            buddy = frame_record(frame_id)["buddy"]
            assert int(alpha[buddy["y"] + buddy["height"] // 2, buddy["x"] + buddy["width"] // 2]) == 255
        else:
            assert 0.58 <= span <= 0.74, (frame_id, round(span, 3))
            opaque = int((region > 200).sum())
            assert 0 < opaque < int(region.size * 0.25), frame_id
            left = []
            for row in range(y + h // 5, y + (4 * h) // 5, max(1, h // 20)):
                cols = np.where(hole[row, x:x + w])[0]
                if len(cols):
                    left.append(int(cols[0]))
            assert max(left) - min(left) > 8, (frame_id, left)


def test_neural_voices_follow_the_character():
    from backend.audio_out import neural_voice
    assert neural_voice("male") == "en-US-GuyNeural"
    assert neural_voice("female") == "en-US-JennyNeural"
    assert neural_voice("nope") == "en-US-GuyNeural"


def test_menu_stays_outside_the_game_hole():
    from backend.frame_library import PLACEMENTS, frame_record
    from backend.overlay_view import rects_overlap
    for frame_id in ("genesis", "nes", "snes"):
        screen = frame_record(frame_id)["screen"]
        menu = PLACEMENTS[frame_id]["menu"]
        buddy = PLACEMENTS[frame_id]["buddy"]
        hole = (screen["x"], screen["y"], screen["width"], screen["height"])
        box = (menu["x"], menu["y"], menu["width"], menu["height"])
        head = (buddy["x"], buddy["y"], buddy["width"], buddy["height"])
        assert not rects_overlap(hole, box), frame_id
        assert not rects_overlap(hole, head), frame_id


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


def test_rest_pose_faces_left_until_talking():
    from backend.hologram import _pose_sprite, yaw_at
    from backend.hologram_art import frame_rest_pose, get_art
    for t in (0.0, 0.4, 1.1, 2.2, 3.5, 5.0):
        assert yaw_at(t, "idle", "left") <= -0.8
        assert yaw_at(t, "smile", "left") <= -0.8
        assert abs(yaw_at(t, "talk", "left")) <= 0.05
    profile = frame_rest_pose()
    # Male rest is the unmirrored approved-frame cut. The brim points left.
    assert _pose_sprite("male", "idle", -1.0, 0).tobytes() == profile.tobytes()
    assert profile.tobytes() != get_art("male").front["neutral"].tobytes()
    assert _cap_text_present(profile)
    female_rest = get_art("female").rest_left
    assert female_rest.tobytes() != get_art("female").front["neutral"].tobytes()
    assert _cap_text_present(female_rest)
    from backend.config_loader import ROOT
    from backend.hologram_art import brim_faces_left, key_black
    from backend.overlay_view import compose_overlay, layout_boxes
    saved = key_black(Image.open(ROOT / "assets" / "hologram" / "male-rest-from-frame.png").convert("RGB"))
    mirrored = key_black(ImageOps.mirror(saved.convert("RGB")))
    assert brim_faces_left(saved)
    assert not brim_faces_left(mirrored)
    assert brim_faces_left(profile)
    assert profile.tobytes() == saved.tobytes()
    assert brim_faces_left(female_rest)
    assert not brim_faces_left(ImageOps.mirror(female_rest))
    for size in ((1280, 720), (1920, 1080), (2560, 1440)):
        for character in ("male", "female"):
            image = compose_overlay(
                "snes", size, expression="idle", game_running=False, character=character,
            )
            box = layout_boxes("snes", size, game_running=False)["head"]
            crop = image.crop((box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]))
            assert crop.getbbox(), (character, size)
    rest = compose_overlay("snes", (1920, 1080), expression="idle", mouth=0.0)
    talking = compose_overlay("snes", (1920, 1080), expression="talk", mouth=0.9)
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
