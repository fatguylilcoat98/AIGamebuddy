"""Game music and Buddy's own speaker are not someone talking."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brain-patch"))

from noise_gate import RoomEar, keep_transcript  # noqa: E402


def _rms_frames(samples: list[float]) -> list[float]:
    frames = []
    for start in range(0, len(samples) - 320, 320):
        chunk = samples[start:start + 320]
        frames.append(math.sqrt(sum(sample * sample for sample in chunk) / len(chunk)))
    return frames


def _music(seconds: float, level: float, seed: int = 1) -> list[float]:
    rng = random.Random(seed)
    count = int(seconds * 16000)
    samples = []
    for index in range(count):
        tone = math.sin(2 * math.pi * 220 * index / 16000) * 0.55
        noise = (rng.random() * 2 - 1) * 0.45
        samples.append((tone + noise) * level)
    return samples


def _starts(ear: RoomEar, frames: list[float]) -> int:
    # The VAD is wrong on purpose: it calls every music frame speech.
    return sum(1 for rms in frames if ear.frame(rms, True) == "speech_start")


def test_game_music_and_speaker_bleed_are_not_speech():
    ear = RoomEar()
    music = _starts(ear, _rms_frames(_music(3.0, 4000)))
    bleed = _starts(ear, _rms_frames(_music(1.2, 5200, seed=2)))
    assert music == 0
    assert bleed == 0
    assert music + bleed == 0


def test_a_person_over_the_game_still_counts():
    ear = RoomEar()
    assert _starts(ear, _rms_frames(_music(1.0, 4000))) == 0
    floor = ear.floor
    loud = []
    for index in range(18):
        scale = 6.0 if index % 2 == 0 else 3.6
        loud.append(floor * scale)
    assert _starts(ear, loud) == 1


def test_buddy_playing_ignores_the_mic():
    ear = RoomEar()
    ear.gated = True
    assert _starts(ear, [ear.floor * 8] * 40) == 0


def test_short_and_unsure_transcripts_are_dropped():
    assert not keep_transcript("I'm sorry.", 900, 0.7, -1.2)
    assert not keep_transcript("About to be gone.", 900, 0.2, -0.3)
    assert not keep_transcript("yo", 200, 0.1, -0.2)
    assert keep_transcript("nice shot on that koopa", 700, 0.1, -0.3)


if __name__ == "__main__":
    test_game_music_and_speaker_bleed_are_not_speech()
    test_a_person_over_the_game_still_counts()
    test_buddy_playing_ignores_the_mic()
    test_short_and_unsure_transcripts_are_dropped()
    print("game music was not speech")
