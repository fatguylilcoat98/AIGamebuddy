"""The overlay must not capture itself or shrink into its own hole."""
from backend.capture_safety import SafetySwitch, bgra_to_rgb, clamp_overlay_geometry, overlay_may_show_capture
from backend.game_capture import GameCapture
from backend.window_layout import position_foreground_window, select_emulator_hwnd


def test_capture_is_never_drawn_on_the_overlay():
    assert overlay_may_show_capture() is False


def test_bgra_bytes_are_not_read_as_rgb():
    # One pixel, BGRA: blue=255, green=0, red=10, alpha=255.
    # As RGB that is (10, 0, 255), not the pink/red you get from a channel swap.
    raw = bytes([255, 0, 10, 255])
    assert bgra_to_rgb(raw, 1, 1) == bytes([10, 0, 255])


def test_overlay_geometry_clamps_to_the_monitor():
    from backend.capture_safety import fit_frame
    assert clamp_overlay_geometry(1920, 1080, (1920, 1080)) == (1920, 1080)
    assert clamp_overlay_geometry(640, 360, (1920, 1080)) == (1920, 1080)
    assert clamp_overlay_geometry(1280, 720, (2560, 1440)) == (2560, 1440)
    assert fit_frame((1920, 1080)) == (0, 0, 1920, 1080)
    assert fit_frame((2560, 1440)) == (0, 0, 2560, 1440)
    origin_x, origin_y, frame_w, frame_h = fit_frame((2560, 1080))
    assert (frame_w, frame_h) == (1920, 1080)
    assert origin_y == 0
    assert origin_x == (2560 - 1920) // 2


def test_repeated_shrink_disables_capture_and_moves():
    switch = SafetySwitch()
    assert switch.note_geometry((1000, 600), 0.0) is False
    assert switch.note_geometry((700, 400), 1.0) is False
    assert switch.note_geometry((200, 100), 2.0) is True
    assert switch.capture_enabled is False
    assert switch.move_enabled is False
    assert "geometry" in switch.reason


def test_repeated_capture_errors_disable_capture():
    switch = SafetySwitch()
    assert switch.note_error("boom", 0.0) is False
    assert switch.note_error("boom", 1.0) is False
    assert switch.note_error("boom", 2.0) is True
    assert switch.capture_enabled is False


def test_capture_throttle_is_about_one_fps():
    switch = SafetySwitch()
    assert switch.allow_capture(10.0, 0.0) is True
    assert switch.allow_capture(10.2, 10.0) is False
    assert switch.allow_capture(11.1, 10.0) is True
    switch.disable("stopped")
    assert switch.allow_capture(20.0, 10.0) is False


def test_only_an_emulator_window_can_be_moved():
    own = {5}
    windows = [(5, "python.exe"), (9, "notepad.exe"), (12, "retroarch.exe")]
    assert select_emulator_hwnd(windows, own) == 12
    assert select_emulator_hwnd([(5, "retroarch.exe")], own) is None
    assert select_emulator_hwnd([(3, "chrome.exe")], set()) is None
    assert select_emulator_hwnd([(8, "emulationstation.exe")], set()) == 8


def test_no_game_window_means_no_capture():
    capture = GameCapture(own_hwnds={5})
    assert capture.locate([(5, "python.exe"), (9, "notepad.exe")]) is None
    assert capture.snapshot(windows=[(9, "notepad.exe")]) is None


def test_foreground_window_is_not_moved():
    moved = position_foreground_window((0, 0, 100, 100))
    assert moved.ok is False
    assert "did not" in moved.message.lower()


def test_load_a_game_and_the_head_stay_in_the_buddy_box():
    import numpy as np
    from backend.frame_library import PLACEMENTS
    from backend.overlay_view import compose_overlay
    box = PLACEMENTS["snes"]["buddy"]
    hole = (320 + 200, 178 + 160)
    idle = np.array(compose_overlay("snes", (1280, 720), expression="idle", game_running=False))
    talk = np.array(compose_overlay("snes", (1280, 720), expression="talk", mouth=0.9, game_running=False))
    assert max(idle[hole[1], hole[0], :3]) < 40
    assert idle[hole[1], hole[0], 3] == 255
    band = idle[box["y"] + box["height"] - 12:box["y"] + box["height"] - 2, box["x"]:box["x"] + box["width"]]
    assert int((band[:, :, 0] > 180).sum()) > 10
    # The prompt is not painted across the game opening.
    opening = idle[178:178 + 80, 320:320 + 200]
    assert int((opening[:, :, 0] > 180).sum()) == 0
    for image, label in ((idle, "rest"), (talk, "talk")):
        head = image[box["y"]:box["y"] + int(box["height"] * 0.78), box["x"]:box["x"] + box["width"]]
        bright = head.max(axis=2) > 70
        rows = np.where(bright.any(axis=1))[0]
        assert len(rows) > 10, label
        assert rows[0] < head.shape[0] * 0.22, label
        assert rows[-1] > head.shape[0] * 0.75, label


def test_maintain_layout_refuses_to_shrink_the_overlay(tmp_path):
    from tests.test_buddy import session_for
    buddy, _clock, _audio, _model = session_for(tmp_path)
    buddy.start()
    buddy.layout = "full"
    buddy.manage_window = True
    first = buddy.maintain_layout((40, 40), (900, 500), now=0.0)
    assert first.reason == "geometry_clamped"
    buddy.maintain_layout((40, 40), (600, 300), now=1.0)
    tripped = buddy.maintain_layout((40, 40), (200, 100), now=2.0)
    assert tripped.reason == "geometry_clamped"
    assert buddy.safety.move_enabled is False
    assert buddy.safety.capture_enabled is False
    stopped = buddy.maintain_layout((40, 40), (1280, 720), now=3.0)
    assert stopped.reason == "safety_stop"
