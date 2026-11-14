"""pre19: game fills the frame opening, and the game is turned down while Buddy talks."""
from __future__ import annotations

import json
import math


def test_game_fills_the_1592x900_opening_and_crops_top_and_bottom_evenly():
    from backend.retroarch_finder import picture_crop, picture_on_blue, visible_picture
    opening = (408, 258, 1592, 900)
    assert picture_on_blue(opening, fit="fill") == (408, 111, 1592, 1194)
    assert visible_picture(opening, fit="fill") == opening
    top, bottom = picture_crop(opening, fit="fill")
    assert top == bottom == 147


def test_fit_mode_keeps_the_old_centered_picture():
    from backend.retroarch_finder import picture_on_blue
    assert picture_on_blue((408, 258, 1592, 900), fit="fit") == (604, 258, 1200, 900)


def test_default_game_fit_is_wide():
    from backend.config_loader import DEFAULTS
    from backend import retroarch_finder as rf
    assert DEFAULTS["overlay"]["game_fit"] == "wide"
    try:
        assert rf.set_game_fit("fit") == "fit"
        assert rf.set_game_fit("fill") == "fill"
        assert rf.set_game_fit("stretch") == "fill"
        assert rf.set_game_fit("wide") == "wide"
        assert rf.set_game_fit("") == "wide"
        assert rf.GAME_FIT == "wide"
        assert rf.picture_on_blue((408, 258, 1592, 900)) == (386, 196, 1755, 1031)
    finally:
        rf.set_game_fit("wide")


def test_tall_opening_fills_by_height():
    from backend.retroarch_finder import picture_on_blue
    x, y, w, h = picture_on_blue((0, 0, 600, 600), fit="fill")
    assert h == 600 and w == 800 and x == -100 and y == 0


def test_click_cut_leaves_frame_art_at_the_edges():
    from PIL import Image
    from backend.overlay_view import art_free_hole
    canvas = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
    for x in range(40, 60):
        for y in range(10, 14):
            canvas.putpixel((x, y), (200, 100, 50, 255))  # banner dips into the top
    x, y, w, h = art_free_hole(canvas, (10, 10, 80, 60))
    assert y == 14 and x == 10 and w == 80 and h == 56


def test_frame_art_is_unchanged_by_fill():
    """The static frame outside the opening is the same pixels as before."""
    import numpy as np
    from backend import retroarch_finder as rf
    from backend.overlay_view import static_frame
    try:
        rf.set_game_fit("fit")
        before = np.array(static_frame("snes", (2560, 1440), game_running=True))
        rf.set_game_fit("fill")
        after = np.array(static_frame("snes", (2560, 1440), game_running=True))
    finally:
        rf.set_game_fit("wide")
    colorful_before = (before[:, :, 3] > 180) & (before[:, :, :3].max(axis=2) >= 32) & \
        ~((before[:, :, 0] == 0) & (before[:, :, 1] == 40) & (before[:, :, 2] == 220))
    assert np.array_equal(before[colorful_before], after[colorful_before])


def test_retroarch_gets_a_bigger_audio_buffer():
    from backend.game_status import runtime_cfg_lines
    lines = runtime_cfg_lines("")
    assert 'audio_latency = "144"' in lines


def test_soft_limiter_leaves_quiet_audio_and_bends_peaks():
    from backend.brain_link import LIMIT_CEILING, soft_limit
    assert soft_limit([0.1, -0.5]) == [0.1, -0.5]
    loud = soft_limit([1.5, -3.0, 0.95])
    assert all(abs(v) < LIMIT_CEILING + 1e-9 for v in loud)
    assert loud[0] > 0 and loud[1] < 0
    assert loud[2] < 0.95


class _FakeMixer:
    def __init__(self, level=1.0):
        self.level = level
        self.history = []

    def backend(self):
        def get():
            return self.level

        def set_(value):
            self.level = value
            self.history.append(value)
        return [("retroarch", get, set_)]


def test_ducker_drops_about_11_db_and_restores_exactly(tmp_path):
    from backend.game_duck import GameDucker
    mixer = _FakeMixer(0.8)
    state = tmp_path / "duck.json"
    ducker = GameDucker(mixer.backend, db=11, state_path=state, sleep=lambda _s: None)
    ducker._want = True
    ducker.apply()
    assert math.isclose(mixer.level, 0.8 * 10 ** (-11 / 20), rel_tol=1e-6)
    assert json.loads(state.read_text())["volume"] == 0.8
    ducker._want = False
    ducker.apply()
    assert math.isclose(mixer.level, 0.8, rel_tol=1e-9)
    assert not state.exists()
    # The ramp moves in small steps, never a jump to silence.
    assert min(mixer.history) >= 0.8 * 10 ** (-11 / 20) - 1e-9


def test_ducker_recovers_a_level_left_down_by_a_crash(tmp_path):
    from backend.game_duck import GameDucker
    mixer = _FakeMixer(0.25)
    state = tmp_path / "duck.json"
    state.write_text(json.dumps({"volume": 0.9}))
    GameDucker(mixer.backend, state_path=state, sleep=lambda _s: None).recover_now()
    assert mixer.level == 0.9
    assert not state.exists()


def test_ducker_does_nothing_without_a_game(tmp_path):
    from backend.game_duck import GameDucker
    ducker = GameDucker(lambda: [], state_path=tmp_path / "d.json", sleep=lambda _s: None)
    ducker._want = True
    ducker.apply()
    assert ducker.ducks == 0
    assert not (tmp_path / "d.json").exists()


def test_speaker_logs_underruns_once_per_window(caplog):
    import logging
    from backend.brain_link import SampleQueue, Speaker
    speaker = Speaker(SampleQueue())
    speaker.underruns = 3
    with caplog.at_level(logging.WARNING, logger="buddy.brain"):
        speaker.report_underruns(now=100.0)
        speaker.underruns = 4
        speaker.report_underruns(now=101.0)
        speaker.report_underruns(now=111.0)
    lines = [r.getMessage() for r in caplog.records if "underruns" in r.getMessage()]
    assert lines == ["Speaker underruns: 3 new, 3 total.", "Speaker underruns: 1 new, 4 total."]
