"""Mouth level smoothing from Buddy's reply audio.

Same rule as the brain page's MouthFollower: 70 ms peak hold, 45 ms open,
130 ms close. Time-based, so the hologram does not depend on the frame rate.
"""
from __future__ import annotations

import math


class MouthFollower:
    def __init__(self, attack: float = 0.045, release: float = 0.13, hold: float = 0.07) -> None:
        self.attack = attack
        self.release = release
        self.hold = hold
        self.env = 0.0
        self.peak = 0.0
        self.hold_left = 0.0

    def step(self, raw: float, dt: float) -> float:
        level = max(0.0, min(1.0, float(raw)))
        if level >= self.peak:
            self.peak = level
            self.hold_left = self.hold
        else:
            self.hold_left -= max(0.0, float(dt))
            if self.hold_left <= 0:
                self.peak = level
        tau = self.attack if self.peak > self.env else self.release
        if tau <= 0:
            self.env = self.peak
        else:
            self.env += (self.peak - self.env) * (1 - math.exp(-max(0.0, float(dt)) / tau))
        return self.env


def audio_level(samples) -> float:
    """0..1 from float PCM, matching the brain page's RMS window."""
    if samples is None:
        return 0.0
    count = len(samples)
    if count <= 0:
        return 0.0
    total = 0.0
    for sample in samples:
        value = float(sample)
        total += value * value
    rms = (total / count) ** 0.5
    level = (rms - 0.01) / 0.16
    if level < 0:
        return 0.0
    if level > 1:
        return 1.0
    return level
