"""The brain link stays quiet without a config, and the mouth eases like the page."""
import json

from backend.brain_link import brain_attitude, load_brain_config
from backend.mouth_follow import MouthFollower


def test_casual_is_friendly_on_the_brain():
    assert brain_attitude("casual") == "friendly"
    assert brain_attitude("regular") == "friendly"
    assert brain_attitude("friendly") == "friendly"
    assert brain_attitude("sassy") == "sassy"
    assert brain_attitude("extreme") == "extreme"


def test_brain_config_reads_url_and_token(tmp_path):
    path = tmp_path / "brain.json"
    path.write_text(json.dumps({
        "url": "https://buddy.example",
        "token": "desk-token",
    }), encoding="utf-8")
    url, token = load_brain_config(path)
    assert url == "wss://buddy.example/ws"
    assert token == "desk-token"
    assert load_brain_config(tmp_path / "missing.json") == ("", "")


def test_mouth_holds_a_peak_then_closes():
    follower = MouthFollower()
    opened = follower.step(0.9, 0.016)
    held = follower.step(0.05, 0.016)
    assert held >= opened
    closed = opened
    for _ in range(8):
        closed = follower.step(0.0, 0.02)
    assert closed < held
