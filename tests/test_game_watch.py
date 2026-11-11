"""Buddy follows the match, in three different voices, without repeating himself."""
from backend.game_watch import GameWatch
from backend.novelty import similarity
from backend.personas import curses_in, persona_prompt


FRAMES = [
    "Street Fighter II. Chris picked Ryu. Opponent is Ken. Round 1. Both health bars are full.",
    "Street Fighter II. Ryu versus Ken. Round 1. Ryu's health is dropping. Ken is ahead.",
    "Street Fighter II. Round 1 lost. Ken won the round. Ryu health empty.",
    "Street Fighter II. Round 2 started. Ryu versus Ken. Ryu health is full. Comeback round.",
    "Street Fighter II. Round 2. Ryu landed a combo. Ken health is low. Ryu is ahead.",
    "Street Fighter II. Round 2 won. Ryu took the round. Score is tied. Comeback.",
    "Street Fighter II. Round 3. Ryu versus Ken. Both health full. Ryu is on a win streak.",
]


def _play(personality: str) -> tuple[GameWatch, list[str]]:
    watch = GameWatch()
    spoken = []
    for frame in FRAMES:
        watch.update(frame)
        line, source = watch.comment(personality)
        assert source == "follow"
        spoken.append(line)
    return watch, spoken


def test_comments_track_a_lost_round_then_a_comeback():
    watch, spoken = _play("sassy")
    text = "\n".join(spoken).lower()
    loss_at = next(i for i, line in enumerate(spoken) if "lost" in line.lower() and "round" in line.lower())
    back_at = next(i for i, line in enumerate(spoken) if "comeback" in line.lower())
    assert back_at > loss_at
    assert "round 2" in text or "round" in spoken[back_at].lower()
    assert watch.character == "Ryu"
    assert watch.opponent == "Ken"
    assert watch.rounds_lost == 1
    assert watch.rounds_won == 1
    answer = watch.answer("who's winning?", "sassy").lower()
    assert "tied" in answer or "comeback" in answer
    stats = watch.said.repetition()
    assert stats["exact_repeats"] == 0


def test_three_attitudes_do_not_sound_alike():
    spoken = {name: _play(name)[1] for name in ("casual", "sassy", "extreme")}
    assert "friendly" in persona_prompt("casual").lower() or "encouraging" in persona_prompt("casual").lower()
    assert "snarky" in persona_prompt("sassy").lower() or "sarcastic" in persona_prompt("sassy").lower()
    assert "18+" in persona_prompt("extreme")
    casual = "\n".join(spoken["casual"]).lower()
    sassy = "\n".join(spoken["sassy"]).lower()
    extreme = "\n".join(spoken["extreme"]).lower()
    assert not curses_in(casual)
    assert "fuck" not in sassy and "shit" not in sassy
    assert "fuck" in extreme
    for left, right in (("casual", "sassy"), ("sassy", "extreme"), ("casual", "extreme")):
        loss_left = next(line for line in spoken[left] if "lost" in line.lower())
        loss_right = next(line for line in spoken[right] if "lost" in line.lower())
        assert similarity(loss_left, loss_right) < 0.55
        back_left = next(line for line in spoken[left] if "comeback" in line.lower())
        back_right = next(line for line in spoken[right] if "comeback" in line.lower())
        assert similarity(back_left, back_right) < 0.55


def test_a_long_sit_does_not_repeat_lines():
    watch = GameWatch()
    watch.update(FRAMES[0])
    lines = []
    for _ in range(36):
        watch.last_change = "same frame"
        line, _source = watch.comment("sassy")
        lines.append(line)
    stats = watch.said.repetition()
    assert stats["exact_repeats"] == 0
    assert stats["near_dup_rate"] < 0.12
    assert len(set(line.lower() for line in lines)) == len(lines)


def test_casual_loss_stays_clean_and_extreme_roasts_it():
    casual = " ".join(_play("casual")[1]).lower()
    assert "fuck" not in casual and "damn" not in casual
    extreme = _play("extreme")[1]
    assert any("fuck" in line.lower() for line in extreme)


def test_live_model_gets_the_memory_and_is_not_repeated():
    watch = GameWatch()
    watch.update(FRAMES[0])
    seen = {}

    def ask(prompt: str) -> str:
        seen["prompt"] = prompt
        return "Alright, Ryu and Ken, round 1, let's see it."

    line, source = watch.comment("sassy", ask=ask)
    assert source == "llm"
    assert line.startswith("Alright")
    assert "Ryu" in seen["prompt"] and "snarky" in seen["prompt"].lower()
    again, source = watch.comment("sassy", ask=ask)
    assert source == "follow"
    assert again != line
