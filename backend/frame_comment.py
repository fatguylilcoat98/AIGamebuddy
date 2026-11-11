"""Lines that come from a captured game frame.

The vision model is used when it is configured. Otherwise Buddy reads the
pixels himself and says what they show. A stock line is only used when there
is no frame, and that case is labeled canned.
"""
from __future__ import annotations

import io
from collections import deque

from PIL import Image


def describe_frame(jpeg: bytes) -> str:
    """A short factual description of one game screenshot."""
    image = Image.open(io.BytesIO(jpeg)).convert("RGB")
    image.thumbnail((64, 56))
    width, height = image.size
    pixels = list(image.get_flattened_data())
    if not pixels:
        return ""

    def zone(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int]:
        picked = []
        for y in range(int(height * y0), max(int(height * y0) + 1, int(height * y1))):
            for x in range(int(width * x0), max(int(width * x0) + 1, int(width * x1))):
                picked.append(pixels[y * width + x])
        count = max(1, len(picked))
        red = sum(p[0] for p in picked) // count
        green = sum(p[1] for p in picked) // count
        blue = sum(p[2] for p in picked) // count
        return red, green, blue

    left = zone(0.0, 0.3, 0.12, 0.7)
    right = zone(0.88, 0.3, 1.0, 0.7)
    top = zone(0.3, 0.0, 0.7, 0.12)
    center = zone(0.35, 0.35, 0.65, 0.65)
    return (
        f"left RGB {left[0]},{left[1]},{left[2]}; "
        f"right RGB {right[0]},{right[1]},{right[2]}; "
        f"top RGB {top[0]},{top[1]},{top[2]}; "
        f"center RGB {center[0]},{center[1]},{center[2]}"
    )


def _tone(personality: str, kind: str) -> list[str]:
    if personality == "extreme":
        return {
            "death": [
                "Damn, you fucking suck.",
                "That death was ugly. Damn.",
            ],
            "good": [
                "Damn dude, I guess you're not so bad.",
                "Alright, that was actually clean.",
            ],
            "look": [
                "Okay, I see it. {fact}",
                "Don't blink. {fact}",
                "Yeah I'm watching. {fact}",
                "Still here. {fact}",
                "Look at that. {fact}",
                "I caught it. {fact}",
                "Keep your eyes up. {fact}",
                "There it is. {fact}",
            ],
        }[kind]
    if personality == "casual":
        return {
            "death": [
                "That one got you. Shake it off.",
                "Rough life. You've still got this.",
            ],
            "good": [
                "Hey, that was nice.",
                "See? You've got it.",
            ],
            "look": [
                "Okay, so {fact}",
                "I'm looking. {fact}",
                "Right, {fact}",
                "Still with you. {fact}",
                "Here's what I see. {fact}",
                "Checking it again. {fact}",
                "Same screen, new look. {fact}",
                "I see this. {fact}",
            ],
        }[kind]
    return {
        "death": [
            "Wow. That was painful to watch.",
            "You walked right into that.",
        ],
        "good": [
            "Okay, show-off. That was good.",
            "Fine. That one was clean.",
        ],
            "look": [
                "Oh I see it. {fact}",
                "Keep going. {fact}",
                "Yeah, {fact}",
                "Hold on, look. {fact}",
                "I'm still on it. {fact}",
                "Okay okay. {fact}",
                "Don't tune me out. {fact}",
                "Right there. {fact}",
            ],
    }[kind]


def _fact(observation: str) -> str:
    text = " ".join((observation or "").split())
    if not text:
        return "the screen's a mess and I can't tell what just happened."
    lower = text.lower()
    if any(word in lower for word in ("died", "death", "ko", "health empty", "game over")):
        return text[:140]
    return text[:140]


def _kind(observation: str) -> str:
    lower = (observation or "").lower()
    if any(word in lower for word in ("died", "death", "ko", "health empty", "game over")):
        return "death"
    if any(word in lower for word in ("won", "clear", "nice hit", "good play", "level clear")):
        return "good"
    return "look"


class FrameCommentator:
    """Turns one observation into a short line and remembers what was just said."""

    def __init__(self) -> None:
        self.recent: deque[str] = deque(maxlen=8)

    def line(self, observation: str, personality: str, *, have_frame: bool) -> tuple[str, str]:
        if not have_frame or not (observation or "").strip():
            text = "I missed that screen, so I'm not gonna pretend I saw it."
            self.recent.append(text)
            return text, "canned"
        kind = _kind(observation)
        options = _tone(personality if personality in {"casual", "sassy", "extreme"} else "sassy", kind)
        fact = _fact(observation)
        for offset in range(len(options)):
            index = (len(self.recent) + offset) % len(options)
            text = options[index].format(fact=fact)
            if text not in self.recent:
                self.recent.append(text)
                return text, "frame"
        text = options[0].format(fact=fact)
        self.recent.append(text)
        return text, "frame"
