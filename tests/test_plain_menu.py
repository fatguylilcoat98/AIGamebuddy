"""Plain menu words, the test ROM, and a real exit."""
from backend.menu_copy import JARGON, menu_lines
from backend.process_exit import is_buddy_process
from backend.results import ActionResult
from backend.retroarch_menu import controller_setup_commands, retroarch_settings_commands
from backend.snes_test_rom import build_snes_test_rom


def test_menu_uses_plain_words_and_a_check():
    rows = menu_lines("female", "sassy", 40, hidden=False)
    blob = "\n".join(title + " " + note for title, note in rows).lower()
    for word in JARGON:
        assert word not in blob
    titles = [title for title, _note in rows]
    assert any(title.startswith("✓ ") and "Woman" in title for title in titles)
    assert any(title.startswith("✓ ") and "Sassy" in title for title in titles)
    assert any("Man" in title and not title.startswith("✓") for title in titles)
    assert any("Friendly" in title for title in titles)
    assert any("Savage-Extreme" in title for title in titles)
    assert any("Set up my controller" in title for title in titles)
    assert any("RetroArch settings" in title for title in titles)
    assert any("Exit to desktop" in title for title in titles)
    assert any("Pick a game" in title for title in titles)
    assert not any("How I talk to Buddy" in title for title in titles)
    assert any(title == "Just talk" for title in titles)
    assert any("always listening" in note.lower() for _title, note in rows)
    assert any("How much Buddy talks" in title and "Sometimes" in title for title in titles)
    assert any("Save my spot" in title for title in titles)
    assert any("Load my spot" in title for title in titles)
    assert any("18+" in note for _title, note in rows)


def test_controller_setup_opens_the_menu_then_controls():
    assert retroarch_settings_commands() == ["MENU_TOGGLE"]
    closed = controller_setup_commands(menu_already_open=False)
    assert closed[0] == "MENU_TOGGLE"
    assert closed[-1] == "MENU_OK"
    assert closed.count("MENU_DOWN") == 5
    opened = controller_setup_commands(menu_already_open=True)
    assert "MENU_TOGGLE" not in opened
    assert opened[-1] == "MENU_OK"


def test_exit_matches_buddy_and_not_some_other_python():
    assert is_buddy_process(r"C:\Users\Chris\AppData\Local\Buddy\runtime\python.exe -m backend.launcher")
    assert is_buddy_process(r"C:\Users\Chris\AppData\Local\Buddy\RetroArch\retroarch.exe")
    assert not is_buddy_process(r"C:\Python312\python.exe -m pytest")
    assert not is_buddy_process(r"C:\Games\retroarch.exe")


def test_exit_to_desktop_kills_the_listed_processes_and_stops(tmp_path):
    from tests.test_buddy import session_for
    session, _clock, _audio, _model = session_for(tmp_path)
    session.retroarch_pid = 4242
    killed = []
    stopped = []

    def killer(pids):
        killed.extend(pids)

    def stop():
        stopped.append("self")

    result = session.exit_to_desktop(list_pids=lambda: [111, 222], killer=killer, stop_self=stop)
    assert result.ok
    assert killed == [111, 222]
    assert stopped == ["self"]
    assert session.closed


def test_snes_test_rom_is_a_lorom_with_a_reset_vector():
    rom = build_snes_test_rom()
    assert len(rom) == 32 * 1024
    assert rom[0x7FC0:0x7FD5].decode("ascii") == "BUDDY SNES TEST ROM  "
    assert rom[0x7FD5] == 0x20
    assert rom[0x7FFC:0x7FFE] == bytes([0x00, 0x80])


def test_chris_frame_hole_does_not_cover_buddy_or_the_button():
    from backend.frame_library import frame_record
    from backend.overlay_view import rects_overlap
    record = frame_record("snes")
    hole = (record["screen"]["x"], record["screen"]["y"], record["screen"]["width"], record["screen"]["height"])
    buddy = (record["buddy"]["x"], record["buddy"]["y"], record["buddy"]["width"], record["buddy"]["height"])
    button = (record["menu"]["x"], record["menu"]["y"], record["menu"]["width"], record["menu"]["height"])
    assert not rects_overlap(hole, buddy)
    assert not rects_overlap(hole, button)
    assert record["screen"]["width"] > 1000
    assert record["buddy"]["x"] > record["screen"]["x"] + record["screen"]["width"]


class _Client:
    def __init__(self):
        self.sent = []
        self.enabled = True

    def send(self, command, **_kwargs):
        self.sent.append(command)
        return ActionResult(True, "sent")


def test_send_commands_stops_on_the_first_failure():
    from backend.retroarch_menu import send_commands
    client = _Client()

    def fail_second(command, **_kwargs):
        client.sent.append(command)
        if len(client.sent) == 2:
            return ActionResult(False, "no")
        return ActionResult(True, "ok")

    client.send = fail_second
    error = send_commands(client, ["MENU_TOGGLE", "MENU_OK"], pause=0, sleep=lambda _s: None)
    assert error == "no"
    assert client.sent == ["MENU_TOGGLE", "MENU_OK"]
