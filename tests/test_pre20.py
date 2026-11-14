"""pre20: wide stretches the game under the title, controller, and Buddy box."""
from __future__ import annotations

import numpy as np


WIDE_NATIVE = (386, 196, 1755, 1031)
OPENING_NATIVE = (408, 258, 1592, 900)
WELL_NATIVE = (2010, 989, 502, 288)


def test_live_proof_accepts_a_wide_game_instead_of_blue_bars():
    from backend import retroarch_finder as rf
    from backend.frame_proof import prove_snes_screen
    from backend.overlay_view import compose_overlay
    previous = rf.GAME_FIT
    try:
        rf.set_game_fit("wide")
        image = compose_overlay(
            "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
        )
    finally:
        rf.set_game_fit(previous)
    import numpy as np
    from PIL import Image
    array = np.array(image.convert("RGBA"))
    clear = array[:, :, 3] < 16
    # A stand-in for the stretched game, the way the live screenshot includes RetroArch.
    array[clear] = (180, 40, 40, 255)
    shot = Image.fromarray(array, "RGBA").convert("RGB")
    problems = prove_snes_screen(shot, menu_open=False, expect_chrome=False, expect_game=True)
    assert problems == [], problems


def test_wide_is_the_default_and_stretch_still_means_fill():
    from backend import retroarch_finder as rf
    from backend.config_loader import DEFAULTS
    assert rf.GAME_FIT == "wide"
    assert DEFAULTS["overlay"]["game_fit"] == "wide"
    try:
        assert rf.set_game_fit("stretch") == "fill"
        assert rf.set_game_fit("wide") == "wide"
        assert rf.set_game_fit("unknown") == "wide"
    finally:
        rf.set_game_fit("wide")


def test_wide_picture_is_the_stretched_rect_at_1440_and_1080():
    from backend.display_info import hole_screen_rect
    from backend.frame_library import frame_record
    from backend.retroarch_finder import picture_on_blue, WIDE_RECT
    assert WIDE_RECT == WIDE_NATIVE
    screen = frame_record("snes")["screen"]
    opening = hole_screen_rect(screen, (0, 0, 2560, 1440))
    assert opening == OPENING_NATIVE
    assert picture_on_blue(opening, fit="wide") == WIDE_NATIVE
    opening_1080 = hole_screen_rect(screen, (0, 0, 1920, 1080))
    assert picture_on_blue(opening_1080, fit="wide") == (290, 147, 1316, 773)


def test_wide_picture_is_the_default_without_an_explicit_fit():
    from backend.retroarch_finder import picture_on_blue
    assert picture_on_blue(OPENING_NATIVE) == WIDE_NATIVE


def _frame(fit: str, monitor=(2560, 1440), game_running=True):
    from backend import retroarch_finder as rf
    from backend.overlay_view import static_frame
    previous = rf.GAME_FIT
    try:
        rf.set_game_fit(fit)
        return np.array(static_frame("snes", monitor, game_running=game_running))
    finally:
        rf.set_game_fit(previous)


def test_wide_punches_the_near_black_gutters_and_keeps_the_well_opaque():
    from backend.overlay_view import punch_wide_gutters
    from backend import retroarch_finder as rf

    art = _frame("wide")
    wx, wy, ww, wh = WELL_NATIVE
    well = art[wy:wy + wh, wx:wx + ww]
    assert float((well[:, :, 3] > 200).mean()) > 0.95

    # Right gutter between the official opening and the Buddy box, mid-screen.
    right = art[700:900, 2000:2140]
    assert float((right[:, :, 3] < 16).mean()) > 0.80

    # Near-black pixels under the official opening, inside the wide picture,
    # are punched (the controller itself stays, because it is colorful).
    rx, ry, rw, rh = WIDE_NATIVE
    under = art[1158:ry + rh, rx:rx + rw]
    near = under[:, :, :3].max(axis=2) <= 36
    # The Buddy well overlaps this band and stays opaque on purpose.
    well_mask = np.zeros(under.shape[:2], dtype=bool)
    well_mask[max(0, wy - 1158):, max(0, wx - rx):] = True
    punched = near & ~well_mask
    assert float(punched.mean()) > 0.3
    assert float((under[punched, 3] < 16).mean()) > 0.99

    # Nothing outside the wide rect (plus the 2-pixel tuck) is opened.
    pad = 2
    rx, ry, rw, rh = WIDE_NATIVE
    outside = np.ones(art.shape[:2], dtype=bool)
    outside[max(0, ry - pad):ry + rh + pad, max(0, rx - pad):rx + rw + pad] = False
    opened = (art[:, :, 3] < 16) & outside
    # The official opening is already clear and sits inside the wide rect,
    # so the canvas edges and the letterbox must stay sealed.
    assert not opened.any()

    # Colorful art (the title bar, away from the punched hole) stays opaque.
    title = art[40:120, 700:1400]
    colorful = (title[:, :, 3] > 180) & (title[:, :, :3].max(axis=2) >= 32)
    assert float(colorful.mean()) > 0.4

    # punch_wide_gutters is also safe to call on its own.
    from backend.overlay_view import _frame_art
    previous = rf.GAME_FIT
    try:
        rf.set_game_fit("fit")
        sealed = np.array(punch_wide_gutters(_frame_art("snes")))
    finally:
        rf.set_game_fit(previous)
    assert float((sealed[wy:wy + wh, wx:wx + ww, 3] > 200).mean()) > 0.95


def test_wide_has_no_blue_backing_or_blue_fill():
    art = _frame("wide")
    blue = (art[:, :, 0] == 0) & (art[:, :, 1] == 40) & (art[:, :, 2] == 220)
    # The painting itself has a few exact (0, 40, 220) specks. The fill is gone.
    opening = art[258:1158, 408:2000]
    opening_blue = (opening[:, :, 0] == 0) & (opening[:, :, 1] == 40) & (opening[:, :, 2] == 220)
    assert not opening_blue.any()
    gutter = art[700:900, 2000:2140]
    gutter_blue = (gutter[:, :, 0] == 0) & (gutter[:, :, 1] == 40) & (gutter[:, :, 2] == 220)
    assert not gutter_blue.any()
    assert int(blue.sum()) <= 8
    # Fit still paints the opening blue so a rollback looks as it did.
    fit = _frame("fit")
    fit_blue = (fit[:, :, 0] == 0) & (fit[:, :, 1] == 40) & (fit[:, :, 2] == 220)
    assert int(fit_blue.sum()) > 1000


def test_fit_and_fill_leave_the_gutters_sealed():
    for mode in ("fit", "fill"):
        art = _frame(mode)
        right = art[700:900, 2000:2140]
        # Blue or sealed black, never a clear hole out to the Buddy box.
        clear = right[:, :, 3] < 16
        assert float(clear.mean()) < 0.05, mode


def test_wide_click_through_keeps_art_and_opens_the_gutters():
    from backend.overlay_view import art_free_hole, static_frame
    from backend import retroarch_finder as rf
    from PIL import Image

    previous = rf.GAME_FIT
    try:
        rf.set_game_fit("wide")
        static = static_frame("snes", (2560, 1440), game_running=True)
        hole = art_free_hole(static, rf.picture_on_blue(OPENING_NATIVE))
    finally:
        rf.set_game_fit(previous)
    hx, hy, hw, hh = hole
    rx, ry, rw, rh = WIDE_NATIVE
    # The click hole stays inside the wide picture and is trimmed back from
    # the title, the controller, and the Buddy well.
    assert hx >= rx and hy >= ry
    assert hx + hw <= rx + rw and hy + hh <= ry + rh
    assert hy > ry  # title bar stays clickable
    assert hy + hh < ry + rh  # controller stays clickable
    # The well itself stays clickable. Mid-screen gutters may run past its x.
    wx, wy, ww, wh = WELL_NATIVE
    well_x, well_y = wx + ww // 2, wy + wh // 2
    assert not (hx <= well_x < hx + hw and hy <= well_y < hy + hh)

    # A punched right-gutter pixel is inside the click hole.
    gx, gy = 2020, 750
    pixel = static.getpixel((gx, gy))
    assert pixel[3] < 16
    assert hx <= gx < hx + hw and hy <= gy < hy + hh

    # art_free_hole still trims a banner the same way as pre19.
    canvas = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
    for x in range(40, 60):
        for y in range(10, 14):
            canvas.putpixel((x, y), (200, 100, 50, 255))
    x, y, w, h = art_free_hole(canvas, (10, 10, 80, 60))
    assert y == 14 and x == 10 and w == 80 and h == 56
