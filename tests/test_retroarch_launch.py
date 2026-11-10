"""RetroArch discovery and the screen-hole window. No Windows window manager required."""
import json
from pathlib import Path

from backend.config_loader import SAMPLE_PATH, load_config
from backend.display_info import hole_screen_rect
from backend.frame_library import frame_record, scale_rect
from backend.overlay_view import band_slots, layout_boxes, rects_overlap
from backend.results import ActionResult
from backend.retroarch_finder import (
    append_arguments,
    common_exe_candidates,
    content_args,
    hole_append_config,
    locate_retroarch,
    needs_replace,
    save_retroarch_path,
    select_game_hwnd,
    should_close_on_quit,
    split_launch_extra,
    wait_for_hwnd,
)


def _env():
    return {
        "ProgramFiles": "PF",
        "ProgramFiles(x86)": "PFx86",
        "APPDATA": "APP",
        "LOCALAPPDATA": "LOCAL",
        "USERPROFILE": "HOME",
        "PATH": "",
    }


def test_discovery_order_is_config_then_folders_then_registry_then_path():
    env = _env()
    candidates = common_exe_candidates(env)
    win64 = r"C:\RetroArch-Win64\retroarch.exe"
    assert win64 in candidates
    assert any("steamapps" in item.replace("\\", "/").lower() and item.endswith("retroarch.exe") for item in candidates)
    assert any("scoop" in item.lower() and item.endswith("retroarch.exe") for item in candidates)
    assert any(item.endswith("RetroArch" + "/retroarch.exe") or item.endswith("RetroArch\\retroarch.exe") for item in candidates)
    appdata = [item for item in candidates if "APP" in item]
    assert appdata

    assert locate_retroarch(
        r"C:\missing\retroarch.exe", exists=lambda path: path == win64,
        environ=env, registry=[], path_value="",
    ) == win64

    configured = r"D:\Games\retroarch.exe"
    assert locate_retroarch(
        configured, exists=lambda path: path in {configured, win64},
        environ=env, registry=[], path_value="",
    ) == configured

    registered = r"C:\Reg\retroarch.exe"
    on_path = r"C:\Bin\retroarch.exe"
    assert locate_retroarch(
        "", exists=lambda path: path in {registered, on_path},
        environ=env, registry=[registered], path_value=r"C:\Bin",
    ) == registered
    assert locate_retroarch(
        "", exists=lambda path: path == on_path,
        environ=env, registry=[r"C:\nope\retroarch.exe"], path_value=r"C:\Bin",
    ) == on_path
    assert locate_retroarch("", exists=lambda path: False, environ=env, registry=[], path_value="") == ""


def test_save_path_updates_a_user_config_and_leaves_the_sample(tmp_path):
    cfg_path = tmp_path / "buddy.config.json"
    cfg_path.write_text('{"retroarch": {"path": ""}}', encoding="utf-8")
    cfg = load_config(cfg_path)
    exe = r"C:\RetroArch-Win64\retroarch.exe"
    assert save_retroarch_path(cfg, exe) == cfg_path
    assert json.loads(cfg_path.read_text(encoding="utf-8"))["retroarch"]["path"] == exe
    before = SAMPLE_PATH.read_text(encoding="utf-8")
    assert save_retroarch_path(load_config(SAMPLE_PATH), exe) is None
    assert SAMPLE_PATH.read_text(encoding="utf-8") == before


def test_hole_rect_uses_the_same_letterbox_as_the_overlay():
    screen = frame_record("nes")["screen"]
    exact = hole_screen_rect(screen, (0, 0, 1920, 1080))
    scaled = scale_rect(screen, (1920, 1080))
    assert exact == (scaled["x"], scaled["y"], scaled["width"], scaled["height"])
    # 2560x1080 letterboxes a 1920x1080 frame. Independent x/y scale would be wrong.
    # Design pixels scale with the letterboxed frame, not with the raw monitor.
    wide = hole_screen_rect({"x": 80, "y": 40, "width": 1600, "height": 1200}, (1920, 0, 2560, 1080))
    assert wide == (1920 + 320 + 60, 30, 1200, 900)
    assert not needs_replace((10, 20, 100, 80), (12, 21, 101, 82), tolerance=4)
    assert needs_replace(None, (0, 0, 10, 10))
    assert needs_replace((0, 0, 10, 10), (30, 0, 10, 10))


def test_hole_config_is_borderless_and_fills_the_window(tmp_path):
    rect = (120, 80, 900, 700)
    text = hole_append_config(rect)
    assert 'video_fullscreen = "false"' in text
    assert 'video_windowed_fullscreen = "false"' in text
    assert 'video_window_show_decorations = "false"' in text
    assert 'video_window_save_positions = "true"' in text
    assert 'video_scale_integer = "false"' in text
    assert 'video_window_x = "120"' in text
    assert 'video_window_width = "900"' in text
    assert 'video_window_height = "700"' in text
    assert 'custom_viewport_x = "0"' in text
    assert 'custom_viewport_width = "900"' in text
    assert 'custom_viewport_height = "700"' in text
    assert 'input_overlay_enable = "false"' in text
    rom, core = content_args("", "", lambda _path: False)
    args = append_arguments(tmp_path / "buddy-hole.cfg", rom, core)
    assert args == ["--appendconfig", str(tmp_path / "buddy-hole.cfg")]
    rom, core = content_args("game.nes", "core.dll", lambda path: path == "game.nes")
    assert append_arguments(Path("hole.cfg"), rom, core) == ["--appendconfig", "hole.cfg", "game.nes"]
    assert split_launch_extra(["-L", "core.dll", "game.nes"]) == ("game.nes", "core.dll")


def test_hwnd_poll_adopts_retroarch_and_ignores_buddy():
    own = {5}
    windows = [(5, "python.exe", "TkTopLevel"), (9, "notepad.exe", ""), (12, "retroarch.exe", "RetroArch")]
    assert select_game_hwnd(windows, own) == 12
    assert select_game_hwnd([(5, "retroarch.exe", "RetroArch")], own) is None
    assert select_game_hwnd([(8, "game.exe", "RetroArch")], set()) == 8
    assert select_game_hwnd([(3, "emulationstation.exe", "Chrome"), (4, "retroarch.exe", "")], set()) == 4
    ticks = {"t": 0.0}
    calls = {"n": 0}

    def clock():
        return ticks["t"]

    def sleep(dt):
        ticks["t"] += dt

    def poll():
        calls["n"] += 1
        return 15 if calls["n"] >= 3 else None

    assert wait_for_hwnd(poll, timeout=15, interval=0.25, sleep=sleep, clock=clock) == 15
    assert ticks["t"] < 1
    ticks["t"] = 0.0
    assert wait_for_hwnd(lambda: None, timeout=1, interval=0.4, sleep=sleep, clock=clock) is None
    assert ticks["t"] >= 1
    assert should_close_on_quit(launched_by_buddy=True, close_on_quit=False) is False
    assert should_close_on_quit(launched_by_buddy=False, close_on_quit=True) is False
    assert should_close_on_quit(launched_by_buddy=True, close_on_quit=True) is True


def test_find_button_stays_inside_buddy_and_off_the_game():
    for frame_id in ("genesis", "nes", "snes"):
        screen = frame_record(frame_id)["screen"]
        for monitor in ((1280, 720), (1920, 1080), (2560, 1080)):
            boxes = layout_boxes(frame_id, monitor, game_running=False, reserve_button=True)
            button = band_slots(boxes)["button"]
            buddy = boxes["buddy"]
            assert button["x"] >= buddy["x"]
            assert button["y"] >= buddy["y"]
            assert button["x"] + button["width"] <= buddy["x"] + buddy["width"] + 0
            assert button["y"] + button["height"] <= buddy["y"] + buddy["height"]
            hole = hole_screen_rect(screen, (0, 0, monitor[0], monitor[1]))
            assert not rects_overlap(
                (button["x"], button["y"], button["width"], button["height"]), hole,
            )


def test_launch_places_a_new_window_and_adopts_an_existing_one(tmp_path):
    from tests.test_buddy import session_for
    buddy, _clock, _audio, _model = session_for(tmp_path)
    exe = tmp_path / "retroarch.exe"
    exe.write_bytes(b"")
    buddy.retroarch_finder = lambda: str(exe)
    state = {"live": False}
    seen = {}

    def runner(command):
        seen["command"] = list(command)
        state["live"] = True
        return 42

    def windows():
        if state["live"]:
            return [(77, "retroarch.exe", "RetroArch")]
        return []

    buddy.process_runner = runner
    buddy.window_source = windows
    buddy.rect_source = lambda _hwnd: (0, 0, 100, 100)
    placed = []

    def mover(hwnd, rect, _own):
        placed.append((hwnd, rect))
        return ActionResult(True, "moved", reason="moved", data={"hwnd": hwnd, "rect": list(rect)})

    buddy.window_positioner = mover
    hole = (120, 80, 900, 700)
    result = buddy.launch_into_hole(hole)
    assert result.ok
    assert seen["command"][0] == str(exe)
    cfg = Path(seen["command"][seen["command"].index("--appendconfig") + 1])
    text = cfg.read_text(encoding="utf-8")
    assert 'video_window_width = "900"' in text
    assert 'video_fullscreen = "false"' in text
    assert placed == [(77, hole)]
    assert buddy.retroarch_started_by_buddy is True
    assert buddy.retroarch_pid == 42

    buddy.rect_source = lambda _hwnd: hole
    stable = buddy.maintain_layout((0, 0), (1920, 1080), hole=hole)
    assert stable.reason == "stable"
    assert placed == [(77, hole)]

    buddy.rect_source = lambda _hwnd: (1, 1, 50, 50)
    nudged = buddy.maintain_layout((0, 0), (1920, 1080), hole=hole)
    assert nudged.reason == "moved"
    assert placed[-1] == (77, hole)

    stopped = []
    buddy.process_stopper = lambda pid: stopped.append(pid)
    buddy.close()
    assert stopped == []

    other, *_ = session_for(tmp_path)
    other.retroarch_finder = lambda: str(exe)
    other.window_source = lambda: [(9, "retroarch.exe", "RetroArch")]
    other.rect_source = lambda _hwnd: (0, 0, 10, 10)
    other.window_positioner = mover
    other.process_runner = lambda _command: (_ for _ in ()).throw(AssertionError("should adopt"))
    adopted = other.launch_into_hole((4, 5, 6, 7))
    assert adopted.reason == "moved"
    assert placed[-1] == (9, (4, 5, 6, 7))
    assert other.retroarch_started_by_buddy is False
    other.config.data["retroarch"]["close_on_quit"] = True
    other.retroarch_started_by_buddy = True
    other.retroarch_pid = 9
    other.process_stopper = lambda pid: stopped.append(pid)
    other.close()
    assert stopped == [9]


def test_missing_retroarch_does_not_launch(tmp_path):
    from tests.test_buddy import session_for
    buddy, *_ = session_for(tmp_path)
    buddy.retroarch_finder = lambda: ""
    called = []
    buddy.process_runner = lambda command: called.append(command)
    result = buddy.launch_into_hole((0, 0, 100, 80))
    assert result.reason == "retroarch_missing"
    assert result.ok is False
    assert called == []
    assert buddy.retroarch_notice == "RetroArch was not found"
