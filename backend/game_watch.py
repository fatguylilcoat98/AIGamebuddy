"""Rolling memory of the match Buddy is watching.

Each new frame is compared with the last one. The comment talks about what
changed. A live model gets that memory plus the latest frame. Without a model,
the same memory still produces a short line, so a scripted match can prove
the follow-along.
"""
from __future__ import annotations

import re
from collections import deque

from .personas import candidates, persona_prompt
from .said_history import SaidHistory


def _title(name: str) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        return ""
    return cleaned[:1].upper() + cleaned[1:]


def _grab(text: str, pattern: str) -> str:
    found = re.search(pattern, text, flags=re.IGNORECASE)
    if not found:
        return ""
    return _title(found.group(1).strip(" .,"))


class GameWatch:
    """What Buddy remembers from the frames so far."""

    def __init__(self) -> None:
        self.game = ""
        self.character = ""
        self.opponent = ""
        self.round_no = ""
        self.rounds_won = 0
        self.rounds_lost = 0
        self.health = ""
        self.opponent_health = ""
        self.level = ""
        self.deaths = 0
        self.streak = 0
        self.last_event = ""
        self.last_observation = ""
        self.last_change = ""
        self.recent: deque[str] = deque(maxlen=8)
        self.said = SaidHistory()
        self._seen_events: set[str] = set()

    def update(self, observation: str) -> str:
        """Fold one frame into memory. Returns a short description of the change."""
        text = " ".join((observation or "").split())
        if not text:
            self.last_change = ""
            return ""
        previous = self.last_observation
        self.last_observation = text
        lower = text.lower()
        if lower.startswith("street fighter"):
            self.game = "Street Fighter II"
        else:
            named = _grab(text, r"(?:playing|game is)\s+([A-Za-z0-9' ]{2,40})")
            if named:
                self.game = named
        character = _grab(text, r"picked ([A-Za-z][A-Za-z0-9']{1,16})")
        if character and character.lower() not in {"the", "a"}:
            self.character = character
        opponent = _grab(text, r"opponent is ([A-Za-z][A-Za-z0-9']{1,16})")
        if not opponent:
            opponent = _grab(text, r"(?:versus|vs\.?)\s+([A-Za-z][A-Za-z0-9']{1,16})")
        if opponent and opponent.lower() != (self.character or "").lower():
            self.opponent = opponent
        round_no = _grab(text, r"round (\d+)")
        if round_no:
            self.round_no = round_no
        area = _grab(text, r"(?:level|area|stage|world)\s+([A-Za-z0-9][A-Za-z0-9' -]{0,24})")
        if area:
            self.level = area
        player = (self.character or "").lower()
        if "health" in lower and "empty" in lower and (not player or player in lower or "your health" in lower):
            self.health = "empty"
        if any(phrase in lower for phrase in (f"{player}'s health is dropping", f"{player} health is dropping", "your health is dropping", "health is dropping")):
            self.health = "dropping"
        other = (self.opponent or "").lower()
        if other and (f"{other} health is low" in lower or f"{other}'s health is low" in lower):
            self.opponent_health = "low"
        elif "health is low" in lower and player and player not in lower:
            self.opponent_health = "low"
        if "health" in lower and "full" in lower and "low" not in lower:
            self.health = "full"
        event = self._event(lower)
        change = self._apply_event(event, lower)
        if not change and previous and previous.lower() == lower:
            change = "same frame"
        elif not change:
            bits = []
            if self.character:
                bits.append(self.character)
            if self.opponent:
                bits.append(f"against {self.opponent}")
            if self.round_no:
                bits.append(f"round {self.round_no}")
            if self.health:
                bits.append(f"health {self.health}")
            change = ", ".join(bits) if bits else "the screen moved"
        self.last_change = change
        self.last_event = event or self.last_event
        return change

    def _event(self, lower: str) -> str:
        if "round" in lower and "lost" in lower:
            return "round_lost"
        if "won the round" in lower or "took the round" in lower or re.search(r"round \d+ won", lower):
            return "round_won"
        if any(word in lower for word in ("died", "death", "you died")):
            return "death"
        if "comeback" in lower:
            return "comeback"
        player = (self.character or "").lower()
        you_ahead = bool(re.search(rf"\b(?:{re.escape(player) or 'you'}|you|your)\b.{{0,24}}ahead", lower))
        if you_ahead:
            return "ahead"
        if "ahead" in lower or "dropping" in lower or "your health is low" in lower:
            return "health_down"
        if "streak" in lower:
            return "streak"
        if "full" in lower and "health" in lower:
            return "health_full"
        return ""

    def _apply_event(self, event: str, lower: str) -> str:
        if not event:
            return ""
        key = f"{event}:{self.round_no}:{lower[:80]}"
        if key in self._seen_events:
            return ""
        self._seen_events.add(key)
        who = self.opponent or "the other guy"
        you = self.character or "you"
        if event == "round_lost":
            self.rounds_lost += 1
            self.streak = -1 if self.streak >= 0 else self.streak - 1
            self.deaths += 1
            self.health = "empty"
            return f"round {self.round_no or '?'} lost to {who}"
        if event == "round_won":
            self.rounds_won += 1
            self.streak = 1 if self.streak <= 0 else self.streak + 1
            return f"round {self.round_no or '?'} won by {you}"
        if event == "death":
            self.deaths += 1
            self.streak = -1 if self.streak >= 0 else self.streak - 1
            return f"{you} died"
        if event == "comeback":
            return f"comeback in round {self.round_no or '?'}"
        if event == "health_down":
            return f"health is falling in round {self.round_no or '?'}"
        if event == "ahead":
            return f"{you} is ahead in round {self.round_no or '?'}"
        if event == "streak":
            return f"win streak {self.streak}"
        if event == "health_full":
            return f"health is full in round {self.round_no or '?'}"
        return ""

    def context(self) -> str:
        """One block the model can keep in the conversation."""
        parts = []
        if self.game:
            parts.append(f"game={self.game}")
        if self.character:
            parts.append(f"character={self.character}")
        if self.opponent:
            parts.append(f"opponent={self.opponent}")
        if self.round_no:
            parts.append(f"round={self.round_no}")
        parts.append(f"rounds_won={self.rounds_won}")
        parts.append(f"rounds_lost={self.rounds_lost}")
        if self.health:
            parts.append(f"health={self.health}")
        if self.opponent_health:
            parts.append(f"opponent_health={self.opponent_health}")
        if self.level:
            parts.append(f"level={self.level}")
        parts.append(f"deaths={self.deaths}")
        parts.append(f"streak={self.streak}")
        if self.last_change:
            parts.append(f"just_changed={self.last_change}")
        if self.last_observation:
            parts.append(f"latest_frame={self.last_observation[:240]}")
        return "; ".join(parts)

    def prompt(self, personality: str) -> str:
        recent = " | ".join(self.said.lines[-8:]) or "(none)"
        return (
            f"{persona_prompt(personality)}\n"
            "Talk about what just changed. If a draft is close to a line already said, "
            "write a different opener and different wording.\n"
            f"Memory: {self.context()}\n"
            f"Already said: {recent}"
        )

    def player_prompt(self, text: str, personality: str) -> str:
        return (
            self.prompt(personality)
            + f"\nChris just said: {text}\nAnswer him from the memory. One sentence."
        )

    def _snap(self, personality: str) -> dict:
        return {
            "you": self.character or "you",
            "them": self.opponent or "the other guy",
            "rnd": self.round_no or "this",
            "won": self.rounds_won,
            "lost": self.rounds_lost,
            "change": self.last_change,
            "index": len(self.said.lines),
            "personality": personality,
        }

    def comment(self, personality: str, ask=None, history: SaidHistory | None = None) -> tuple[str, str]:
        """One line about the latest change. `ask` is the live model, if it is on."""
        book = history or self.said
        spoken = ""
        if ask is not None and self.last_observation:
            try:
                spoken = " ".join((ask(self.prompt(personality)) or "").split())
            except Exception:
                spoken = ""
        options: list[str] = []
        if spoken:
            options.append(spoken[:220])
        options.extend(candidates(personality, self._snap(personality)))
        line = book.pick(options)
        book.add(line)
        self.recent.append(line)
        source = "llm" if spoken and line == spoken[:220] else "follow"
        return line, source

    def answer(self, text: str, personality: str) -> str:
        """A direct reply when Chris asks about the match and no model is on."""
        lower = (text or "").lower()
        if not any(word in lower for word in (
            "who", "round", "winning", "win", "health", "score", "happened", "how's", "how is", "how're",
        )):
            return ""
        if not (self.character or self.opponent or self.rounds_won or self.rounds_lost):
            return ""
        you = self.character or "you"
        them = self.opponent or "the other guy"
        if personality == "extreme" and self.rounds_lost > self.rounds_won:
            return (
                f"You're {you} against {them}. Rounds are {self.rounds_won} for you and "
                f"{self.rounds_lost} for {them}. Yeah, you're down."
            )
        if self.rounds_won and self.rounds_lost and self.rounds_won == self.rounds_lost:
            return (
                f"You're {you} against {them}. You lost one and took the next. "
                f"It's {self.rounds_won}-{self.rounds_lost}, so the comeback tied it."
            )
        return (
            f"You're {you} against {them}. Round {self.round_no or '1'}, "
            f"{self.rounds_won} won and {self.rounds_lost} lost."
        )

    def _local_line(self, personality: str) -> str:
        you = self.character or "you"
        them = self.opponent or "the other guy"
        rnd = self.round_no or "this"
        change = self.last_change
        if change.startswith("round") and "lost" in change:
            if personality == "extreme":
                return f"Damn, round {rnd} is gone. You fucking lost that one to {them}."
            if personality == "casual":
                return f"Round {rnd} got away. {them} took it. That's {self.rounds_lost} down."
            return f"Round {rnd} is lost. {them} took it."
        if change.startswith("round") and "won" in change:
            if self.rounds_lost:
                if personality == "extreme":
                    return (
                        f"Damn dude, I guess you're not so bad. You took round {rnd}. "
                        f"Comeback. It's {self.rounds_won}-{self.rounds_lost}."
                    )
                return (
                    f"You took round {rnd}. Comeback. "
                    f"It's {self.rounds_won} won and {self.rounds_lost} lost."
                )
            return f"You took round {rnd}. That's {self.rounds_won} for {you}."
        if "died" in change:
            if personality == "extreme":
                return "Damn, you fucking suck. Shake it off and go again."
            if personality == "casual":
                return "That one got you. Load back in."
            return "Oof, that death counted. You're still in it."
        if change.startswith("health is falling"):
            return f"{them}'s got the edge. Your health is dropping in round {rnd}."
        if "ahead" in change:
            return f"You're ahead in round {rnd}. {them}'s health is the one in trouble."
        if change.startswith("comeback"):
            return f"Round {rnd}. Health's back. This is the comeback."
        if change.startswith("health is full"):
            if self.rounds_lost and not self.rounds_won:
                return f"Round {rnd}. Health's back. This is the comeback."
            return f"Round {rnd}. {you} against {them}, health's full."
        if "streak" in change:
            return f"Round {rnd}, and you're on a streak."
        if self.character and self.opponent and self.round_no:
            return f"You're {you} against {them}. Round {rnd}, health {self.health or 'up'}."
        return "I'm still on the screen with you."

    def _hold_line(self) -> str:
        you = self.character or "you"
        them = self.opponent or "them"
        return (
            f"Still {you} and {them}. "
            f"Score's {self.rounds_won} to {self.rounds_lost}, round {self.round_no or '1'}."
        )
