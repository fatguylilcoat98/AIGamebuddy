"""Frame lines, help, and the cartoon rig."""
from backend.cartoon_buddy import render_booth, render_cartoon
from backend.frame_comment import FrameCommentator, describe_frame
from backend.game_help import known_help, lookup_help


def test_extreme_roasts_a_death_and_casual_stays_clean():
    extreme = FrameCommentator()
    line, source = extreme.line("the player died, health empty", "extreme", have_frame=True)
    assert source == "frame"
    assert "fucking suck" in line.lower() or "damn" in line.lower()
    casual = FrameCommentator()
    clean, _source = casual.line("the player died, health empty", "casual", have_frame=True)
    assert "fuck" not in clean.lower()
    assert "damn" not in clean.lower()
    respect, _source = extreme.line("nice hit, good play", "extreme", have_frame=True)
    assert "not so bad" in respect.lower() or "clean" in respect.lower()
    missed, canned = extreme.line("", "sassy", have_frame=False)
    assert canned == "canned"
    assert missed


def test_contra_code_and_an_unsure_lookup():
    assert "Konami" in known_help("Contra", "what's the cheat code")
    line, source = lookup_help("Moon Patrol", "where is the last stage", fetch=lambda _query: "")
    assert source == "unsure"
    assert "not sure" in line.lower()
    line, source = lookup_help("Contra", "cheat code", fetch=lambda _query: "unused")
    assert source == "known"


def test_cartoon_frames_are_not_a_single_tilt():
    from io import BytesIO
    left = render_cartoon(160, t=0.2, yaw=-0.9, mouth=0.0, expression="idle", talking=False)
    player = render_cartoon(160, t=0.2, yaw=0.0, mouth=0.8, expression="talk", talking=True)
    laugh = render_cartoon(160, t=0.2, yaw=0.0, mouth=0.9, expression="laugh", talking=True)
    later = render_cartoon(160, t=1.1, yaw=-0.9, mouth=0.0, expression="idle", talking=False)
    assert left.tobytes() != player.tobytes()
    assert player.tobytes() != laugh.tobytes()
    assert left.tobytes() != later.tobytes()
    booth = render_booth(180, 0.4, -0.4, 0.7, "talk", "female")
    assert booth.size == (180, 180)
    # A described frame mentions both sides, so a line can use them.
    image = left.convert("RGB")
    buf = BytesIO()
    image.save(buf, format="JPEG")
    text = describe_frame(buf.getvalue())
    assert "left RGB" in text and "right RGB" in text
