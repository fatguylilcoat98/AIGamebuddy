"""Expression state driven by model tags and gameplay events."""
from __future__ import annotations

import re
from dataclasses import dataclass

EXPRESSIONS = (
    "idle", "blink", "talk", "smile", "wink", "laugh", "smug", "shocked", "celebrate", "sad",
)

TAG = re.compile(r"\[(emotion|gaze|angle|callback|silence):([a-z0-9_]+)\]", re.IGNORECASE)

EVENT_EXPRESSIONS = {
    "death": "sad",
    "crash": "shocked",
    "loss": "sad",
    "game_over": "sad",
    "win": "celebrate",
    "level_clear": "celebrate",
    "boss": "smug",
}


@dataclass
class TagParse:
    text: str
    emotion: str
    gaze: str | None
    angle: str | None
    callback: bool
    silence: bool


def parse_tags(raw: str) -> TagParse:
    emotion = ""
    gaze = None
    angle = None
    callback = False
    silence = False

    def repl(match: re.Match) -> str:
        nonlocal emotion, gaze, angle, callback, silence
        kind = match.group(1).lower()
        value = match.group(2).lower()
        if kind == "emotion" and value in EXPRESSIONS:
            emotion = value
        elif kind == "gaze" and value in {"left", "right", "up", "down", "center"}:
            gaze = value
        elif kind == "angle" and re.fullmatch(r"[a-z0-9_]+", value):
            angle = value
        elif kind == "callback":
            callback = True
        elif kind == "silence":
            silence = True
        return ""

    text = TAG.sub(repl, raw or "").strip()
    if text.lower() in {"[silence]", "silence"}:
        silence = True
        text = ""
    if silence:
        text = ""
    return TagParse(text=text, emotion=emotion or ("talk" if text else "idle"), gaze=gaze,
                    angle=angle, callback=callback, silence=silence)


class EmotionDirector:
    """Holds the current expression until its hold time expires, then returns to idle."""

    def __init__(self) -> None:
        self.expression = "idle"
        self.from_expression = "idle"
        self.blend_started: float | None = None
        self.gaze = "center"
        self.hold_until = 0.0
        self.mouth = 0.0
        self.speaking = False

    def set_expression(self, name: str, now: float, hold_s: float = 2.4) -> None:
        if name not in EXPRESSIONS:
            name = "idle"
        if name != self.expression:
            self.from_expression = self.expression
            self.blend_started = now
        self.expression = name
        self.hold_until = now + max(0.2, hold_s)

    def set_gaze(self, gaze: str | None) -> None:
        if gaze:
            self.gaze = gaze

    def on_event(self, kind: str, now: float) -> None:
        name = EVENT_EXPRESSIONS.get(kind)
        if name:
            self.set_expression(name, now, 2.8)

    def apply_parse(self, parsed: TagParse, now: float) -> None:
        self.set_gaze(parsed.gaze)
        if parsed.silence:
            self.set_expression("idle", now, 0.4)
            return
        self.set_expression(parsed.emotion, now, 3.0 if parsed.emotion in {"laugh", "celebrate"} else 2.4)

    def tick(self, now: float, *, speaking: bool, mouth: float) -> None:
        self.speaking = speaking
        self.mouth = max(0.0, min(1.0, mouth))
        if speaking and self.expression in {"idle", "blink"}:
            self.set_expression("talk", now, 0.4)
        elif now >= self.hold_until and not speaking and self.expression != "idle":
            self.set_expression("idle", now, 0.2)
            self.mouth = 0.0

    def snapshot(self, now: float | None = None) -> dict:
        blend = 1.0
        if now is not None and self.blend_started is not None:
            blend = max(0.0, min(1.0, (now - self.blend_started) / 0.28))
        return {
            "expression": self.expression,
            "from_expression": self.from_expression,
            "expression_blend": round(blend, 3),
            "gaze": self.gaze,
            "mouth": round(self.mouth, 3),
            "speaking": self.speaking,
        }
