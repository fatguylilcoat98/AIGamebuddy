"""Tests for memory, banter packs, novelty, commands, and the session."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.audio_out import AudioDevice, AudioOutput, resolve_device
from backend.buddy_brain import BuddyBrain
from backend.buddy_session import BuddySession
from backend.config_loader import SAMPLE_PATH, load_config, strip_json_comments
from backend.detection import parse_snapshot
from backend.emotions import parse_tags
from backend.game_session import GameSession
from backend.memory_store import MemoryStore
from backend.novelty import NoveltyEngine, families_in, similarity
from backend.personality_pack import PackError, load_angles, load_pack, validate_tree
from backend.providers import chat, validate_url
from backend.results import ActionResult, ModelResult
from backend.takeover import evaluate_gate
from backend.window_layout import emulator_target, position_foreground_window

ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0
        self.m = 5_000.0

    def unix(self):
        return self.t

    def mono(self):
        return self.m

    def advance(self, seconds):
        self.t += seconds
        self.m += seconds


class ScriptModel:
    def __init__(self, lines):
        self.lines = list(lines)
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        if not self.lines:
            return ModelResult("", "fake", error="offline")
        return ModelResult(self.lines.pop(0), "fake")


class FakeAudio:
    def __init__(self):
        self.lines = []
        self.speaking = False

    def speak(self, text, **kwargs):
        self.lines.append(text)
        return ActionResult(True, "Played audio on test.", reason="played")

    def devices(self):
        return [{"index": 1, "name": "Cable Output"}]

    def stop(self):
        self.speaking = False


def config_for(tmp_path):
    cfg = load_config(SAMPLE_PATH)
    cfg.data["data_dir"] = str(tmp_path)
    cfg.data["provider"] = "offline"
    cfg.data["takeover"]["enabled"] = False
    return cfg


def session_for(tmp_path, *, model=None, personality="sassy"):
    cfg = config_for(tmp_path)
    cfg.data["personality"] = personality
    memory = MemoryStore(tmp_path / "buddy.sqlite3")
    clock = Clock()
    audio = FakeAudio()
    model = model if model is not None else ScriptModel([])
    buddy = BuddySession(cfg, memory=memory, clock=clock, model=model, audio=audio)
    return buddy, clock, audio, model


def test_packs_validate():
    errors = validate_tree()
    assert errors == []
    angles = load_angles()
    assert len(angles) == 20
    assert "faceplant" in [item.id for item in angles["death"]]
    assert "tadpole" in [item.id for item in angles["fishing_catch_small"]]
    assert "reset_spicy" in [item.id for item in angles["death"]]
    for mode in ("casual", "sassy", "extreme"):
        pack = load_pack(mode)
        assert len(pack.seeds) == 20
        assert sum(len(lines) for lines in pack.seeds.values()) >= 200
        assert sum(len(lines) for lines in pack.templates.values()) >= 50
        assert "Voice" in pack.style
        assert "zion" not in pack.style.lower()


def test_broken_pack_is_rejected(tmp_path):
    folder = tmp_path / "casual"
    folder.mkdir()
    (folder / "STYLE.md").write_text("too short", encoding="utf-8")
    (folder / "seeds.json").write_text("{}", encoding="utf-8")
    (folder / "templates.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ANTI-REPETITION.md").write_text(Path("data/personalities/ANTI-REPETITION.md").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(PackError) as caught:
        load_pack("casual", tmp_path)
    assert caught.value.errors


def test_similarity_and_families():
    score = similarity("You suck at jumping", "You're terrible at jumping")
    assert score >= 0.62
    assert similarity("Nice clear landing", "You suck at jumping") < 0.62
    assert families_in("look at that little tadpole") & families_in("snack fish, pocket-sized")
    assert families_in("you fucking suck right now") & families_in("bro you suck")
    assert "one_pixel" in families_in("one pixel more and you had it")
    assert "one_pixel" in families_in("that was a frame away")
    assert "bed" in families_in("you are crapping the bed")


def test_angle_rotation_and_category_gap(tmp_path):
    memory = MemoryStore(tmp_path / "m.sqlite3")
    engine = NoveltyEngine(memory)
    now = 1_700_000_000.0
    memory.add_line(unix=now, personality="sassy", category="death", text="Unique faceplant gag number one.",
                    emotion="smug", game_title=None, callback=False, angle="faceplant")
    blocked = engine.screen("A totally different death sentence about spacing.", category="death",
                            angle="spacing_fail", personality="sassy", now=now + 30, priority=1)
    assert blocked.allow is False
    assert blocked.reason == "category_cooldown"
    later = engine.screen("A totally different death sentence about spacing.", category="death",
                          angle="faceplant", personality="sassy", now=now + 400, priority=1)
    assert later.allow is False
    assert later.reason == "angle_back_to_back"
    fresh = engine.screen("A totally different death sentence about spacing.", category="death",
                          angle="spacing_fail", personality="sassy", now=now + 400, priority=1)
    assert fresh.allow is True


def test_metaphor_family_blocks_for_a_day(tmp_path):
    memory = MemoryStore(tmp_path / "m.sqlite3")
    engine = NoveltyEngine(memory)
    now = 1_700_000_000.0
    memory.add_line(unix=now, personality="extreme", category="fishing_catch_small",
                    text="Look at that little tadpole.", emotion="smug", game_title=None,
                    callback=False, angle="tadpole")
    blocked = engine.screen("Snack fish. Pocket-sized at best.", category="fishing_catch_small",
                            angle="snack_sized", personality="extreme", now=now + 3600, priority=3)
    assert blocked.allow is False
    assert blocked.reason.startswith("metaphor_family")
    allowed = engine.screen("Snack fish. Pocket-sized at best.", category="fishing_catch_small",
                            angle="snack_sized", personality="extreme", now=now + 25 * 3600, priority=3)
    assert allowed.reason != blocked.reason or allowed.allow


def test_callback_can_reference_history_but_not_copy_a_gag(tmp_path):
    memory = MemoryStore(tmp_path / "m.sqlite3")
    engine = NoveltyEngine(memory)
    now = 1_700_000_000.0
    memory.add_line(unix=now, personality="sassy", category="death", text="That wipe was sloppy.",
                    emotion="smug", game_title="Excitebike", callback=False, angle="faceplant")
    decision = engine.screen(
        "Last time you wiped out on this track.",
        category="callback_to_past_session", angle="redeem_the_l", personality="sassy",
        now=now + 500, allow_callback=True, priority=2,
    )
    assert decision.allow is True
    assert decision.callback is True
    memory.add_line(unix=now + 500, personality="sassy", category="callback_to_past_session",
                    text="Last time you wiped out on this track.", emotion="smug",
                    game_title="Excitebike", callback=True, angle="redeem_the_l")
    again = engine.screen(
        "Last time you wiped out on this track.",
        category="callback_to_past_session", angle="redeem_the_l", personality="sassy",
        now=now + 800, allow_callback=True, callbacks_this_session=0, priority=2,
    )
    assert again.allow is False


def test_session_does_not_play_seeds_and_fills_a_template(tmp_path):
    buddy, clock, audio, _model = session_for(tmp_path, personality="casual")
    buddy.start()
    buddy.memory.add_event(unix=clock.unix(), session_id=buddy.session_id, game_title=None,
                           kind="death", detail="a hit", source="observed", confidence=0.9)
    buddy.memory.add_event(unix=clock.unix(), session_id=buddy.session_id, game_title=None,
                           kind="death", detail="a hit", source="observed", confidence=0.9)
    result = buddy._banter(player_text="", spontaneous=True, event="death", priority=3, direct=False)
    seeds = {line.strip().lower() for line in buddy.pack.seeds["death"]}
    assert result.text.strip().lower() not in seeds
    assert "2" in result.text
    assert audio.lines[-1] == result.text


def test_repeated_model_joke_is_dropped(tmp_path):
    line = "[emotion:smug][angle:faceplant] Brand new spacing note: stand one step back."
    model = ScriptModel([line, line])
    buddy, clock, audio, model = session_for(tmp_path, model=model, personality="sassy")
    buddy.start()
    first = buddy._banter(player_text="", spontaneous=True, event="death", priority=3, direct=False)
    assert "one step back" in first.text
    assert first.spoken is True
    clock.advance(400)
    second = buddy._banter(player_text="", spontaneous=True, event="death", priority=3, direct=False)
    assert second.text == ""
    assert audio.lines == [first.text]


def test_stop_insulting_blocks_the_roast(tmp_path):
    model = ScriptModel(["[emotion:laugh][angle:mash_punish] You fucking suck at this. Hold block."])
    buddy, _clock, audio, _model = session_for(tmp_path, model=model, personality="extreme")
    buddy.start()
    stopped = buddy.handle_text("Buddy, stop insulting me")
    assert stopped.ok
    assert "stop insulting" in stopped.text.lower() or "stop insulting" in stopped.message.lower()
    reply = buddy.handle_text("how do I beat this boss")
    assert "fucking" not in reply.text.lower()
    assert "suck" not in reply.text.lower()


def test_missing_emulator_is_a_real_failure(tmp_path):
    buddy, _clock, audio, _model = session_for(tmp_path)
    buddy.start()
    result = buddy.handle_text("open RetroArch")
    assert result.ok is False
    assert "did not" in result.message.lower()
    assert any("did not" in line.lower() for line in audio.lines)


def test_takeover_gate_never_claims_control(tmp_path):
    denied = evaluate_gate(mode="takeover", game_title="Street Fighter II", window_title="Street Fighter II - RetroArch",
                           user_confirmed_offline=True, enabled=False)
    assert denied.allowed is False
    online = evaluate_gate(mode="takeover", game_title="Street Fighter II", window_title="Fightcade lobby",
                           user_confirmed_offline=True, enabled=True)
    assert online.allowed is False
    assert "did not" in online.message.lower()
    buddy, _clock, _audio, _model = session_for(tmp_path)
    buddy.config.data["takeover"]["enabled"] = True
    buddy.start()
    buddy.offline_confirmed = True
    buddy.identity.title = "Street Fighter II"
    buddy.identity.window_title = "Street Fighter II - RetroArch"
    buddy.identity.uncertain = False
    result = buddy.request_takeover()
    assert result.ok is False
    assert "did not" in result.message.lower() or "no input" in result.message.lower()
    unknown = buddy.handle_text("you play")
    # identity is still SF2, so permission can open, but control must still be reported as not sent
    assert unknown.ok is False


def test_memory_survives_a_new_session(tmp_path):
    buddy, clock, _audio, _model = session_for(tmp_path)
    buddy.start()
    buddy.handle_text("switch to extreme")
    buddy.memory.add_event(unix=clock.unix(), session_id=buddy.session_id, game_title="Excitebike",
                           kind="death", detail="missed the landing", source="observed", confidence=0.95)
    path = buddy.memory.path
    buddy.close()
    cfg = config_for(tmp_path)
    again = BuddySession(cfg, memory=MemoryStore(path), clock=clock, model=ScriptModel([]), audio=FakeAudio())
    again.start()
    summary = again.memory.summary()
    assert "extreme" in summary.lower() or again.personality == "extreme"
    assert "Excitebike" in summary or again.memory.count_events("death", "Excitebike") == 1
    cleared = again.clear_memory()
    assert cleared.ok
    assert again.memory.count_events("death") == 0


def test_window_title_is_not_treated_as_vision(tmp_path):
    snapshot = GameSession(True, True, "Street Fighter II - RetroArch", "retroarch.exe", "RetroArch", True, (0, 0, 10, 10))
    identity = parse_snapshot(snapshot)
    assert identity.title == "Street Fighter II"
    assert "visually confirmed" in identity.factual_line() or "have not visually" in identity.factual_line()
    assert "I can see" not in identity.factual_line()
    empty = parse_snapshot(GameSession(False, False, None, None, None, False, None))
    assert "Windows" in empty.factual_line()


def test_commands_and_layout_do_not_pretend(tmp_path):
    buddy, _clock, _audio, _model = session_for(tmp_path)
    buddy.start()
    theme = buddy.handle_text("switch to the purple overlay")
    assert theme.ok
    assert buddy.theme == "snes"
    assert "did not launch" in theme.message.lower()
    found = buddy.handle_text("find excitebike")
    assert found.ok is False
    moved = position_foreground_window((0, 0, 100, 100))
    assert moved.ok is False
    assert "did not" in moved.message.lower()
    origin = emulator_target((10, 20), (1280, 720))
    assert origin[2] > 0 and origin[3] > 0


def test_provider_rejects_bad_urls_and_redacts(tmp_path):
    cfg = config_for(tmp_path)
    cfg.data["provider"] = "ollama"
    cfg.data["ollama"]["model"] = "llama3.2"
    seen = {}

    def transport(url, payload, headers, timeout, allow_loopback):
        seen["url"] = url
        seen["loopback"] = allow_loopback
        return 200, {"message": {"content": "ok"}}

    result = chat(cfg, [{"role": "user", "content": "hi"}], transport=transport)
    assert result.text == "ok"
    assert seen["url"].startswith("http://127.0.0.1:11434/")
    with pytest.raises(Exception):
        validate_url("http://example.com/v1", allow_loopback_http=True)
    cfg.data["provider"] = "meta"
    cfg.data["meta"]["model"] = "muse"
    cfg.data["meta"]["base_url"] = "https://api.meta.ai/v1"
    import os
    os.environ["BUDDY_META_API_KEY"] = "secret-token-value"

    def boom(url, payload, headers, timeout, allow_loopback):
        return 401, {"error": {"message": "bad secret-token-value"}}

    failed = chat(cfg, [{"role": "user", "content": "hi"}], transport=boom)
    assert "secret-token-value" not in failed.error
    assert "[redacted]" in failed.error
    del os.environ["BUDDY_META_API_KEY"]


def test_sample_config_has_no_secrets_and_zion_is_renamed(tmp_path):
    text = SAMPLE_PATH.read_text(encoding="utf-8")
    assert "sk-" not in text
    assert "api_key\"" not in text
    assert "Zion" not in text
    raw = strip_json_comments('{ "a": "keep // this", "b": 1 } // no')
    assert json.loads(raw)["a"] == "keep // this"
    cfg = load_config(SAMPLE_PATH)
    cfg.data["character_name"] = "Zion"
    # load_config is what enforces the name; repeat that rule
    from backend.config_loader import load_config as load_again
    path = tmp_path / "buddy.config.json"
    path.write_text(json.dumps({"character_name": "Zion", "product_name": "Working Title"}), encoding="utf-8")
    loaded = load_again(path)
    assert loaded.get("character_name") == "Buddy"
    assert loaded.warnings


def test_uncertain_vision_text_is_not_an_event():
    from backend.vision_service import parse_vision_text
    plain = parse_vision_text("maybe a fight, I am not sure")
    assert plain["uncertain"] is True
    assert plain["event"] == "none"
    sure = parse_vision_text('{"summary":"The round was lost.","game_guess":"Street Fighter II","game_confidence":0.9,"event":"lose_round","event_confidence":0.92,"uncertain":false}')
    assert sure["event"] == "lose_round"
    assert sure["uncertain"] is False
    weak = parse_vision_text('{"summary":"hard to tell","event":"death","event_confidence":0.2,"uncertain":false}')
    assert weak["event"] == "none"
    assert weak["uncertain"] is True


def test_emotion_tags_and_brain_still_gate():
    parsed = parse_tags("[emotion:smug][angle:faceplant] Hello there")
    assert parsed.emotion == "smug"
    assert parsed.angle == "faceplant"
    assert parsed.text == "Hello there"
    assert parse_tags("[silence]").silence
    brain = BuddyBrain(cooldown_seconds=10)
    assert brain.decide("landed", 2, now=0).should_speak
    brain.mark_spoken("landed", now=0)
    assert brain.decide("a different thing happened", 1, now=3).reason == "cooldown"


def test_audio_device_must_exist():
    devices = [AudioDevice(1, "Cable Output"), AudioDevice(2, "Speakers")]
    assert resolve_device("cable", devices).name == "Cable Output"
    assert resolve_device("nope", devices) is None
    assert resolve_device("", devices).name == "default"


def test_character_and_resting_direction_switch(tmp_path):
    buddy, _clock, _audio, _model = session_for(tmp_path)
    buddy.start()
    assert buddy.buddy_character == "male"
    assert buddy.resting_direction == "left"
    female = buddy.handle_text("switch to female buddy")
    assert female.ok
    assert buddy.buddy_character == "female"
    assert buddy.character == "Buddy"
    right = buddy.handle_text("rest right")
    assert right.ok
    assert buddy.resting_direction == "right"
    bad = buddy.set_buddy_character("zion")
    assert bad.ok is False
    assert buddy.buddy_character == "female"


def test_speak_never_raises_when_portaudio_is_missing():
    def explode():
        raise OSError("PortAudio library not found")

    audio = AudioOutput(device_lister=explode, synthesizer=lambda text, rate: b"RIFF", player=explode)
    result = audio.speak("hello", volume=40, rate=0, device_name="", mute=False)
    assert result.ok is False
    assert result.reason == "playback_failed"


def test_menu_action_refreshes_before_a_throw():
    from backend.overlay_app import run_menu_action
    seen = []

    def mutate():
        seen.append("mutate")

    def refresh():
        seen.append("refresh")

    def announce():
        seen.append("announce")
        raise OSError("audio")

    run_menu_action(mutate, refresh, announce)
    assert seen == ["mutate", "refresh", "announce", "refresh"]


def test_hotkey_edges_and_quit_keysym():
    from backend.hotkeys import QUIT_SEQUENCES, poll_hotkey_events, tk_quit_event
    assert "<Control-Shift-Q>" in QUIT_SEQUENCES
    previous = {"f8": False, "f9": False, "quit": False}
    assert poll_hotkey_events(previous, {"f8": False, "f9": True, "quit": False}) == ["talk_down"]
    assert poll_hotkey_events({"f9": True}, {"f8": False, "f9": False, "quit": False}) == ["talk_up"]
    assert poll_hotkey_events(previous, {"f8": True, "f9": False, "quit": True}) == ["menu", "quit"]

    class Event:
        keysym = "Q"
        state = 0x1 | 0x4

    assert tk_quit_event(Event())
    Event.keysym = "q"
    Event.state = 0x4
    assert tk_quit_event(Event()) is False


def test_local_api_health():
    import json
    import socket
    import threading
    import time
    import urllib.request
    import uvicorn
    from backend.main import app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="buddy-api-test", daemon=True)
    thread.start()
    body = None
    last_error = None
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                body = json.loads(response.read().decode())
            break
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    server.should_exit = True
    thread.join(timeout=5)
    assert body is not None, last_error
    assert body["status"] == "ok"
    assert body["character"] == "Buddy"


def test_every_mode_fills_fifty_death_lines(tmp_path):
    fallback = "i don't have a fresh line"
    for personality in ("casual", "sassy", "extreme"):
        folder = tmp_path / personality
        folder.mkdir()
        buddy, clock, _audio, _model = session_for(folder, personality=personality)
        buddy.start()
        lines = []
        for index in range(60):
            buddy.memory.add_event(
                unix=clock.unix(), session_id=buddy.session_id, game_title=None,
                kind="death", detail=f"hit {index}", source="observed", confidence=0.9,
            )
            clock.advance(2 * 3600)
            result = buddy._banter(
                player_text="", spontaneous=False, event="death", priority=3, direct=True,
            )
            text = (result.text or "").strip()
            assert fallback not in text.lower()
            assert fallback not in (result.message or "").lower()
            assert text
            lines.append(text)
        assert len(lines) >= 50
        assert len({line.lower() for line in lines}) >= 50


def test_clear_and_reset_are_distinct(tmp_path):
    buddy, clock, _audio, _model = session_for(tmp_path)
    buddy.start()
    buddy.memory.add_line(unix=clock.unix(), personality="sassy", category="death", text="one unique line",
                          emotion="sad", game_title=None, callback=False, angle="faceplant")
    buddy.reset_memory()
    assert buddy.memory.recent_lines()
    buddy.clear_memory()
    assert buddy.memory.recent_lines() == []
