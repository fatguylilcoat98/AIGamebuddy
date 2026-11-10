"""Setup wizard rules. No Windows installer and no ROM files are required."""
import json
from pathlib import Path

from backend.display_info import hole_screen_rect
from backend.frame_library import frame_record
from backend.game_status import (
    announce_line,
    parse_get_status,
    shader_relative,
    stuck_line,
    write_core_shader_presets,
)
from backend.overlay_view import layout_boxes, rects_overlap
from backend.setup_catalog import blocked_cores, default_cores
from backend.setup_flow import (
    GAMES_COPY,
    SECRET_NAME,
    MemoryVault,
    apply_config,
    can_leave,
    config_contains_secret,
    create_games_tree,
    fetch_verified,
    fresh_state,
    games_list_rect,
    install_default_cores,
    install_portable,
    load_state,
    move,
    reject_blocked_core,
    save_state,
    scan_games,
    sha256_file,
    check_stored_key,
    verify_sha256,
)
from backend.wizard_pages import SHOTS, write_shots


def test_default_cores_are_commercial_ok_and_the_others_are_flagged():
    names = [core.name for core in default_cores()]
    assert names == ["FCEUmm", "bsnes", "BlastEm"]
    blocked = {core.name for core in blocked_cores()}
    assert blocked == {"Snes9x", "PicoDrive", "Genesis Plus GX"}
    assert "not install" in reject_blocked_core("snes9x_libretro.dll").lower() or "did not install" in reject_blocked_core("snes9x_libretro.dll").lower()
    assert reject_blocked_core("fceumm_libretro.dll") == ""


def test_checksum_mismatch_and_unpinned_files_are_refused(tmp_path):
    payload = b"retroarch-bytes"
    path = tmp_path / "retroarch.exe"
    path.write_bytes(payload)
    digest = sha256_file(path)
    assert verify_sha256(path, digest) == ""
    assert "did not match" in verify_sha256(path, "a" * 64)
    assert "not pinned" in verify_sha256(path, "")
    seen = []

    def progress(_fraction, message):
        seen.append(message)

    error = fetch_verified(
        {"name": "RetroArch", "version": "1.22.1", "url": "https://example.invalid/ra.7z", "sha256": ""},
        tmp_path / "out.7z",
        lambda _url: b"nope",
        progress,
    )
    assert "not pinned" in error
    assert not (tmp_path / "out.7z").exists()


def test_portable_install_copies_only_matching_gpl_cores(tmp_path):
    bundle = tmp_path / "bundle"
    cores = bundle / "cores"
    cores.mkdir(parents=True)
    exe = bundle / "retroarch.exe"
    exe.write_bytes(b"retroarch")
    blobs = {}
    for core in default_cores():
        data = core.filename.encode("utf-8")
        (cores / core.filename).write_bytes(data)
        blobs[core.filename] = sha256_file(cores / core.filename)
    (cores / "snes9x_libretro.dll").write_bytes(b"do-not-ship")
    blobs["retroarch.exe"] = sha256_file(exe)
    dest = tmp_path / "Buddy" / "RetroArch"
    assert install_portable(bundle, dest, blobs, lambda *_args: None) == ""
    installed, skipped, error = install_default_cores(cores, dest / "cores", blobs, lambda *_args: None)
    assert error == ""
    assert installed == [core.filename for core in default_cores()]
    assert any("Snes9x" in item for item in skipped)
    assert not (dest / "cores" / "snes9x_libretro.dll").exists()
    guest = dest / "shaders" / "shaders_slang" / "crt" / "crt-guest-advanced-ntsc.slangp"
    guest.parent.mkdir(parents=True)
    guest.write_text("guest", encoding="utf-8")
    assert shader_relative(dest).endswith("crt-guest-advanced-ntsc.slangp")
    assert write_core_shader_presets(dest).endswith("crt-guest-advanced-ntsc.slangp")
    guest.unlink()
    light = dest / "shaders" / "shaders_slang" / "crt" / "crt-geom.slangp"
    light.parent.mkdir(parents=True, exist_ok=True)
    light.write_text("geom", encoding="utf-8")
    assert shader_relative(dest).endswith("crt-geom.slangp")
    light.unlink()
    assert shader_relative(dest) == ""


def test_games_folder_lists_owned_files_and_does_not_link_anywhere(tmp_path):
    assert "http" not in GAMES_COPY.lower()
    assert "www." not in GAMES_COPY.lower()
    root = create_games_tree(tmp_path / "Buddy Games")
    (root / "NES").joinpath("Owned.nes").write_bytes(b"nes")
    (root / "NES").joinpath("notes.txt").write_text("not a rom", encoding="utf-8")
    (root / "NES").joinpath("skip.bin").write_bytes(b"bin")
    (root / "SNES").mkdir(exist_ok=True)
    (root / "Genesis").joinpath("Owned.md").write_bytes(b"md")
    (root / "Genesis").joinpath("Owned.bin").write_bytes(b"bin")
    found = scan_games(root)
    assert found["nes"] == ["Owned.nes"]
    assert found["snes"] == []
    assert found["genesis"] == ["Owned.bin", "Owned.md"]


def test_wizard_resumes_and_extreme_needs_a_yes():
    state = fresh_state()
    assert move(state, 1) == ""
    assert state["step"] == "install"
    assert "Install RetroArch" in can_leave(state)
    state["retroarch_path"] = r"C:\Buddy\retroarch.exe"
    assert move(state, 1) == ""
    assert state["step"] == "games"
    state["games_dir"] = r"C:\Users\Chris\Buddy Games"
    assert move(state, 1) == ""
    assert move(state, 1) == ""
    state["personality"] = "extreme"
    state["extreme_confirmed"] = False
    assert "18" in move(state, 1)
    assert state["step"] == "ai"
    state["extreme_confirmed"] = True
    assert move(state, 1) == ""
    assert state["step"] == "buddy"


def test_api_key_stays_out_of_the_config(tmp_path):
    from backend.config_loader import load_config
    from backend.config_loader import SAMPLE_PATH
    vault = MemoryVault()
    secret = "super-secret-value"
    assert vault.put(SECRET_NAME, secret) == ""
    assert secret not in check_stored_key(vault)
    called = {}

    def transport(url, key):
        called["url"] = url
        called["key"] = key
        return 200, {}

    assert "worked" in check_stored_key(vault, transport).lower()
    assert called["key"] == secret
    assert "secret" not in called["url"]
    cfg = load_config(SAMPLE_PATH)
    cfg.path = tmp_path / "buddy.config.json"
    state = fresh_state()
    state["retroarch_path"] = str(tmp_path / "retroarch.exe")
    state["games_dir"] = str(tmp_path / "Buddy Games")
    state["api_key_stored"] = True
    apply_config(cfg, state)
    text = json.dumps(cfg.data)
    assert not config_contains_secret(text, secret)
    assert "super-secret-value" not in text
    assert cfg.data["retroarch"]["command_enabled"] is True
    assert cfg.data["retroarch"]["command_port"] == 55355
    path = save_state(state, tmp_path / "Buddy" / "setup-state.json")
    loaded = load_state(path)
    assert loaded["step"] == state["step"]
    assert "api_key" not in loaded


def test_status_parses_crc_and_the_shorter_reply():
    older = parse_get_status("GET_STATUS PLAYING nes,Owned Game,crc32=AbC")
    assert older.state == "PLAYING"
    assert older.system == "nes"
    assert older.game == "Owned Game"
    assert older.crc == "abc"
    newer = parse_get_status("GET_STATUS PAUSED Super Nintendo Entertainment System,Dungeon")
    assert newer.state == "PAUSED"
    assert newer.system == "snes"
    assert newer.game == "Dungeon"
    assert newer.crc == ""
    genesis = parse_get_status("GET_STATUS PLAYING mega_drive,Streets,crc32=10,core=blastem")
    assert genesis.system == "genesis"
    assert genesis.core == "blastem"
    assert parse_get_status("GET_STATUS CONTENTLESS").game == ""
    assert "Super NES" in announce_line("Owned Game", "snes")
    assert "http" not in stuck_line("extreme", "Owned Game")
    assert "item you already have" in stuck_line("extreme", "Owned Game")
    assert "fuck" not in stuck_line("casual", "Owned Game").lower()


def test_game_list_stays_in_buddy_and_status_is_spoken(tmp_path):
    from tests.test_buddy import session_for
    for frame_id in ("nes", "snes", "genesis"):
        boxes = layout_boxes(frame_id, (1920, 1080), game_running=True)
        rect = games_list_rect(boxes["buddy"])
        buddy = boxes["buddy"]
        assert rect["x"] >= buddy["x"]
        assert rect["y"] + rect["height"] <= buddy["y"] + buddy["height"]
        hole = hole_screen_rect(frame_record(frame_id)["screen"], (0, 0, 1920, 1080))
        assert not rects_overlap((rect["x"], rect["y"], rect["width"], rect["height"]), hole)
    buddy, _clock, audio, _model = session_for(tmp_path)
    buddy.commands.enabled = True
    buddy.commands.port = 55355
    buddy.personality = "extreme"
    replies = iter([
        "GET_STATUS PAUSED nes,Owned Game,crc32=abc",
        "GET_STATUS PAUSED nes,Owned Game,crc32=abc",
    ])
    buddy.status_query = lambda: next(replies)
    buddy.poll_game_status(now=0)
    buddy.poll_game_status(now=50)
    assert any("Owned Game" in line and "NES" in line for line in audio.lines)
    assert any("item you already have" in line for line in audio.lines)


def test_wizard_pages_render(tmp_path):
    assert len(SHOTS) == 13
    steps = [step for _name, step, _extra in SHOTS]
    assert steps[0] == "welcome"
    assert steps[-1] == "done"
    written = write_shots(tmp_path)
    assert len(written) == 13
    for path in written:
        assert path.stat().st_size > 8000
