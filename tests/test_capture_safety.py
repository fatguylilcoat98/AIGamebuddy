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


def test_overlay_geometry_clamps_back_to_the_frame():
    assert clamp_overlay_geometry(1280, 720) == (1280, 720)
    assert clamp_overlay_geometry(640, 360) == (1280, 720)
    assert clamp_overlay_geometry(2, 2) == (1280, 720)
    assert clamp_overlay_geometry(1920, 1080) == (1280, 720)


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
