"""pre21: hands-free talk and a look every look_interval, no 9s/20s gates."""
from tests.test_buddy import session_for


def test_start_talking_is_handsfree_and_does_not_open_a_second_mic(tmp_path):
    session, _clock, _audio, _model = session_for(tmp_path)
    assert session._ears is None
    result = session.start_talking()
    assert result.ok
    assert result.reason == "handsfree"
    assert session._ears is None
    done = session.finish_talking()
    assert done.reason == "handsfree"
    assert session._ears is None


def test_looks_send_every_interval_without_a_nine_or_twenty_second_gate(tmp_path, monkeypatch):
    session, clock, _audio, _model = session_for(tmp_path)
    session.look_interval = 5
    session.frequency = "chatty"
    sent = []

    class FakeBrain:
        def push_game(self, text, react, picture=""):
            sent.append({"t": clock.mono(), "react": react, "picture": bool(picture), "text": text})
            return True

    session._brain = FakeBrain()
    session._game_visible = lambda: True
    session._capture_game_window = lambda: (320, 224, b"jpeg-bytes")
    monkeypatch.setattr(
        "backend.frame_comment.prepare_game_jpeg",
        lambda _jpeg, _last: ("pic-" + str(clock.mono()), b"thumb-" + str(int(clock.mono())).encode(), None),
    )

    session._look_worker()
    clock.advance(5)
    session._look_worker()
    clock.advance(5)
    session._look_worker()
    assert len(sent) == 3
    assert all(item["react"] is True for item in sent)
    gaps = [sent[i]["t"] - sent[i - 1]["t"] for i in range(1, len(sent))]
    assert gaps == [5, 5]


def test_menu_hides_talk_mode_and_says_just_talk():
    from backend.menu_copy import menu_lines
    rows = menu_lines("male", "extreme", 60, hidden=False, talk_amount="chatty", look_interval=5)
    titles = [title for title, _note in rows]
    assert "Just talk" in titles
    assert not any("How I talk to Buddy" in title for title in titles)
    assert not any("Hold a button" in title for title in titles)
    assert any("always listening" in note.lower() for _title, note in rows)


def test_s16le_chunks_enqueue_immediately_without_an_mp3_clip():
    import json
    import struct
    from backend.brain_link import BrainLink, _s16le_to_float

    pcm = struct.pack("<4h", 0, 16384, -16384, 32767)
    samples = _s16le_to_float(pcm)
    assert len(samples) == 4
    assert abs(samples[1] - 0.5) < 0.01

    class Session:
        muted = False
        volume = 100
        mouth = 0.0
        _brain_speaking = False

    class DummySpeaker:
        rate = 24000

        def start(self):
            self.started = True

        def stop(self):
            pass

    link = BrainLink(Session())
    try:
        link._speaker = DummySpeaker()
        header = json.dumps({"seq": 7, "fmt": "s16le", "rate": 24000, "ch": 1, "part": 0, "fin": False}).encode()
        payload = len(header).to_bytes(4, "little") + header + pcm
        before_clips = list(link._clips)
        link._on_audio(payload)
        assert link._clips == before_clips
        assert link._output.pending() == 4
        assert link._out_seq == 7
    finally:
        link.close()



def test_animate_keeps_the_head_visible_while_the_menu_is_open():
    from backend.overlay_app import MENU_OPEN_ANIMATE_MS, LIVE_ANIMATE_MS, animate_delay_ms, should_paint_head
    assert LIVE_ANIMATE_MS <= 33
    # ~5 fps so the well stays filled without fighting the menu thread.
    assert 180 <= MENU_OPEN_ANIMATE_MS <= 250
    assert animate_delay_ms(False) == LIVE_ANIMATE_MS
    assert animate_delay_ms(True) == MENU_OPEN_ANIMATE_MS
    assert should_paint_head(False) is True
    assert should_paint_head(True) is True


def test_game_fit_and_talk_settings_save_to_ui_state(tmp_path):
    from tests.test_buddy import session_for
    session, _clock, _audio, _model = session_for(tmp_path)
    session.set_game_fit("fit")
    session.set_talk_amount("chatty")
    session.set_look_interval(5)
    saved = session._ui_path().read_text(encoding="utf-8")
    assert '"game_fit": "fit"' in saved
    assert '"frequency": "chatty"' in saved
    assert '"look_interval": 5' in saved
    session.game_fit = "wide"
    session.frequency = "normal"
    session.look_interval = 10
    session._load_ui()
    assert session.game_fit == "fit"
    assert session.frequency == "chatty"
    assert session.look_interval == 5


def test_compact_menu_builds_and_dropdowns_call_the_session(tmp_path):
    import tkinter as tk
    from backend.hamburger_ui import HamburgerMenu
    from tests.test_buddy import session_for

    session, _clock, _audio, _model = session_for(tmp_path)
    session.frequency = "normal"
    session.look_interval = 10
    session.game_fit = "wide"
    root = tk.Tk()
    root.geometry("1280x720+40+40")
    root.update()
    try:
        changes = []
        menu = HamburgerMenu(root, session, lambda: changes.append("changed"))
        menu.toggle()
        root.update()
        root.update_idletasks()
        assert menu.open
        assert menu.panel.state() != "withdrawn"
        # No hanging canvas scrollbar when the page is short enough, or it is packed only if needed.
        menu._talk_amount("chatty")
        assert session.frequency == "chatty"
        menu._look_every(5)
        assert session.look_interval == 5
        menu._game_fit("fit")
        assert session.game_fit == "fit"
        titles = [child.cget("text") for child in menu.inner.winfo_children() if child.winfo_class() in {"Label", "Button", "Checkbutton"}]
        blob = " ".join(str(t) for t in titles)
        assert "How I talk to Buddy" not in blob
        assert "Announcer booth" not in blob
        assert menu._tips, "every setting should have a hover tip"
        menu.close()
        assert not menu.open
    finally:
        root.destroy()



def _boxes_ok(boxes):
    attitude = boxes.get("Buddy attitude")
    volume = boxes.get("Volume")
    assert attitude, f"Buddy attitude label missing, have {list(boxes)}"
    assert volume, f"Volume label missing, have {list(boxes)}"
    ax, ay, aw, ah = attitude[:4]
    vx, vy, vw, vh = volume[:4]
    assert ah >= 12, f"Buddy attitude is clipped, height={ah}"
    assert vh >= 12, f"Volume is clipped, height={vh}"
    assert aw >= 40 and vw >= 20
    # No overlap: attitude row must end above (or at) the volume row.
    assert ay + ah <= vy + 2, f"rows overlap: attitude y={ay}+{ah} volume y={vy}"


def test_menu_first_paint_is_complete_and_stable(tmp_path):
    """Opening the menu must finish layout before the first paint, and
    hovering rows must not jump or clip the attitude/volume rows."""
    import tkinter as tk
    from backend.hamburger_ui import HamburgerMenu
    from tests.test_buddy import session_for

    session, _clock, _audio, _model = session_for(tmp_path)
    session.frequency = "chatty"
    session.look_interval = 5
    session.game_fit = "wide"
    session.volume = 70
    root = tk.Tk()
    root.geometry("1280x720+40+40")
    root.update()
    try:
        menu = HamburgerMenu(root, session, lambda: None)
        menu.toggle()
        # First paint: no extra waits. sync_layout finished inside toggle().
        assert menu.panel.winfo_viewable()
        content_h = int(menu.inner.winfo_reqheight())
        panel_h = int(menu.panel.winfo_height())
        assert panel_h >= 240
        assert panel_h <= content_h + 48, f"panel too tall: {panel_h} vs content {content_h}"
        assert panel_h < int(root.winfo_height()) - 80, f"panel fills the window: {panel_h}"
        first = menu.row_geometry()
        _boxes_ok(first)
        snapshots = [first]
        for _ in range(4):
            root.update()
            snapshots.append(menu.row_geometry())
            _boxes_ok(snapshots[-1])
        # Hover every row (show each tooltip, then hide it).
        for tip in list(menu._tips):
            tip.show()
            root.update()
            snapshots.append(menu.row_geometry())
            _boxes_ok(snapshots[-1])
            tip.hide()
            root.update()
            snapshots.append(menu.row_geometry())
            _boxes_ok(snapshots[-1])
        key = ("Buddy attitude", "Volume")
        first_pos = {name: snapshots[0][name][:4] for name in key}
        for i, shot in enumerate(snapshots[1:], start=1):
            for name in key:
                assert shot[name][:4] == first_pos[name], (
                    f"{name} moved after paint {i}: {first_pos[name]} -> {shot[name][:4]}"
                )
        menu.close()
    finally:
        root.destroy()
