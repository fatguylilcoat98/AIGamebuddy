"""Save slots, the upgrade frame reset, and how much Buddy talks."""
from backend.commands import match_intent
from backend.frame_migration import FRAME_REVISION, migrate_saved_theme
from backend.hologram import render_hologram, step_yaw
from backend.save_slots import has_continue, load_commands, remember_save, save_commands
from backend.talk_input import is_wake_phrase, shoulder_hold, utterance_after_wake


def test_save_walks_to_the_slot_and_load_names_it():
    save = save_commands(2)
    assert save[:16] == ["STATE_SLOT_MINUS"] * 16
    assert save[16:18] == ["STATE_SLOT_PLUS", "STATE_SLOT_PLUS"]
    assert save[-1] == "SAVE_STATE"
    assert "pause_nonactive" not in " ".join(save)
    assert load_commands(3) == ["LOAD_STATE_SLOT 3"]


def test_saves_stay_with_the_game(tmp_path):
    remember_save(tmp_path, r"C:\Games\Street Fighter II.sfc", 1)
    remember_save(tmp_path, r"C:\Games\Street Fighter II.sfc", 0)
    assert has_continue(tmp_path, r"C:\Games\Street Fighter II.sfc")
    from backend.save_slots import has_slot
    assert has_slot(tmp_path, r"C:\Games\Street Fighter II.sfc", 1)
    assert not has_slot(tmp_path, r"C:\Games\Other.sfc", 1)


def test_an_old_theme_becomes_the_snes_frame_once(tmp_path):
    stamp = tmp_path / "frame-revision.txt"
    first = migrate_saved_theme({"theme": "genesis", "theme_mode": "auto"}, stamp)
    assert first["theme"] == "snes"
    assert first["theme_mode"] == "snes"
    assert stamp.read_text(encoding="utf-8").strip() == FRAME_REVISION
    again = migrate_saved_theme({"theme": "genesis", "theme_mode": "genesis"}, stamp)
    assert again["theme"] == "genesis"


def test_talk_commands_and_the_wake_phrase():
    assert match_intent("Buddy, you're talking too much").name == "talk_less"
    assert match_intent("Buddy, you can talk more").name == "talk_more"
    assert match_intent("Buddy, be quiet").name == "quiet_until_called"
    assert match_intent("mute").name == "mute"
    assert is_wake_phrase("Hey Buddy, look at this")
    assert utterance_after_wake("Hey Buddy, look at this") == "look at this"
    events, held = shoulder_hold(False, True, 0.0, 0.3)
    assert events == []
    events, held = shoulder_hold(True, True, held, 0.3)
    assert events == ["shoulders_talk_down"]
    events, _held = shoulder_hold(True, False, held, 0.03)
    assert events == ["shoulders_talk_up"]


def test_talking_turns_toward_the_player_and_rest_stays_left():
    rest = render_hologram("idle", t=0.4, mouth=0.0, size=180, character="male", yaw=-0.92)
    talk = render_hologram("talk", t=0.4, mouth=0.9, size=180, character="male", yaw=0.0)
    assert rest.tobytes() != talk.tobytes()
    assert step_yaw(-0.92, 0.0) > -0.92
    assert step_yaw(-0.2, -0.92) < -0.2


def test_save_spot_sends_the_retroarch_commands(tmp_path):
    from tests.test_buddy import session_for
    session, _clock, _audio, _model = session_for(tmp_path)
    session.current_rom = r"C:\Games\Street Fighter II.sfc"
    sent = []

    class Client:
        enabled = True
        host = "127.0.0.1"
        port = 55355

        def send(self, command, **_kwargs):
            from backend.results import ActionResult
            sent.append(command)
            return ActionResult(True, "sent")

    session.commands = Client()
    result = session.save_spot(1)
    assert result.ok
    assert sent[-1] == "SAVE_STATE"
    assert sent.count("STATE_SLOT_PLUS") == 1
    assert session.has_continue(session.current_rom) is False
    loaded = session.load_spot(1)
    assert loaded.ok
    assert sent[-1] == "LOAD_STATE_SLOT 1"
