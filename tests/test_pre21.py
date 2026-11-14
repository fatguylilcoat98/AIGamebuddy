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
