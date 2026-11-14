"""Novelty gate: similarity, angle rotation, category gaps, metaphor families.

Rules follow data/personalities/ANTI-REPETITION.md. A blocked line is not spoken.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
import re

from .memory_store import MemoryStore
from .personality_pack import COOLDOWNS

WORD = re.compile(r"[a-z0-9']+")
FILLER = {"dude", "bro", "alright", "okay", "ok", "damn", "hey", "just", "like", "really", "uh", "um"}

SYNONYM_GROUPS = {
    "bad": "suck sucks terrible awful horrible bad trash garbage hopeless pathetic",
    "jump": "jump jumping jumps hop hopping hopped",
    "crash": "crash crashed crashing wreck wrecked wipe wiped dirt",
    "die": "die died dead death killed",
    "win": "win won victory victorious cleared",
    "boss": "boss",
    "land": "land landing landed",
    "you": "you youre youre",
}
TOKEN_TO_CANON: dict[str, str] = {}
for _canon, _words in SYNONYM_GROUPS.items():
    for _word in _words.split():
        TOKEN_TO_CANON[_word] = _canon

# Phrase families from ANTI-REPETITION.md. Hitting one member blocks the family.
METAPHOR_FAMILIES: dict[str, tuple[str, ...]] = {
    "tiny_fish": ("tadpole", "snack fish", "snack-sized", "snack sized", "pocket-sized",
                  "pocket sized", "booster seat", "micro win"),
    "you_suck": ("you fucking suck", "you suck", "bro you suck"),
    "bed": ("crapping the bed", "shitting the bed", "bed is a mess"),
    "one_pixel": ("one pixel", "frame away", "hair early", "almost famous"),
    "down_back": ("down-back", "down back"),
    "main_character": ("main character", "protagonist"),
    "pad_please": ("give me the controller", "gimme the pad", "hand me the pad", "pad please"),
    "i_got_you": ("i've got this", "i got this", "i got you"),
    "welcome_back": ("missed you", "welcome back"),
    "librarian": ("i'll look it up", "i will look it up", "let me look it up", "librarian mode"),
    "lake_laughing": ("lake is laughing", "lake's laughing", "lake laughing"),
    "from_the_dirt": ("from the dirt", "from the grave"),
    "keep_the_receipt": ("keep the receipt",),
    "gps_buddy": ("i'll be your gps", "i will be your gps", "gps buddy"),
}

HELP_CATEGORIES = {"player_asks_help", "stuck_where_to_go"}
SIMILARITY_THRESHOLD = 0.62


def tokens(text: str) -> list[str]:
    raw = WORD.findall(text.lower().replace("'", ""))
    return [word for word in raw if word not in FILLER]


def canonicalize(words: list[str]) -> list[str]:
    return [TOKEN_TO_CANON.get(word, word) for word in words]


def jaccard(a: list[str], b: list[str]) -> float:
    left, right = set(a), set(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    seq = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    return 0.40 * seq + 0.45 * jaccard(canonicalize(ta), canonicalize(tb)) + 0.15 * jaccard(ta, tb)


def families_in(text: str) -> set[str]:
    lowered = text.lower().replace("'", "")
    found = set()
    for name, phrases in METAPHOR_FAMILIES.items():
        if any(phrase in lowered for phrase in phrases):
            found.add(name)
    return found


def _parse_iso(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def looks_like_callback(text: str) -> bool:
    lowered = text.lower()
    return "last time" in lowered or "remember" in lowered or "last session" in lowered or any(ch.isdigit() for ch in text)


@dataclass(frozen=True)
class NoveltyDecision:
    allow: bool
    reason: str
    score: float = 0.0
    callback: bool = False

    def to_dict(self) -> dict:
        return {"allow": self.allow, "reason": self.reason, "score": round(self.score, 3), "callback": self.callback}


class NoveltyEngine:
    def __init__(self, memory: MemoryStore):
        self.memory = memory

    def screen(self, text: str, *, category: str, angle: str, personality: str, now: float,
               direct: bool = False, allow_callback: bool = False, priority: int = 1,
               callbacks_this_session: int = 0, frequency: str = "normal") -> NoveltyDecision:
        cleaned = " ".join((text or "").split())
        if category == "status":
            return NoveltyDecision(True, "status")
        if not cleaned:
            return NoveltyDecision(False, "empty")
        limits = dict(COOLDOWNS.get(personality, COOLDOWNS["sassy"]))
        if frequency == "rare":
            limits["angle_minutes"] *= 1.5
            limits["category_seconds"] *= 2
        elif frequency == "chatty":
            limits["angle_minutes"] = max(20, limits["angle_minutes"] * 0.67)
            limits["category_seconds"] = limits["priority_category_seconds"]

        rows = self.memory.recent_lines(500)
        best = 0.0
        best_callback = 0.0
        category_age = None
        angle_age = None
        last_angle = None
        family_age: dict[str, float] = {}
        mine = families_in(cleaned)
        for row in rows:
            age = now - _parse_iso(row["at"])
            if age < 0:
                continue
            score = similarity(cleaned, row["text"])
            if row["callback"]:
                best_callback = max(best_callback, score)
            else:
                best = max(best, score)
            if row["category"] == category and category_age is None:
                category_age = age
                last_angle = row.get("angle") or None
            if angle and row["category"] == category and row.get("angle") == angle and angle_age is None:
                angle_age = age
            for family in families_in(row["text"]) & mine:
                family_age.setdefault(family, age)

        callback_attempt = (
            allow_callback
            and category == "callback_to_past_session"
            and callbacks_this_session < 1
            and looks_like_callback(cleaned)
        )
        similar_score = best_callback if callback_attempt else max(best, best_callback)
        if similar_score >= SIMILARITY_THRESHOLD:
            return NoveltyDecision(False, "too_similar", similar_score)
        blocked_family = None
        for family, age in family_age.items():
            if family == "down_back" and direct and category in HELP_CATEGORIES:
                continue
            if age < limits["metaphor_hours"] * 3600:
                blocked_family = family
                break
        if blocked_family:
            return NoveltyDecision(False, f"metaphor_family:{blocked_family}", similar_score)
        if callback_attempt:
            return NoveltyDecision(True, "intentional_callback", similar_score, callback=True)

        if category == "chat":
            return NoveltyDecision(True, "chat", similar_score)
        if category == "idle":
            if category_age is not None and category_age < limits["idle_seconds"]:
                return NoveltyDecision(False, "idle_quiet", similar_score)
        if angle:
            if last_angle and angle == last_angle:
                return NoveltyDecision(False, "angle_back_to_back", similar_score)
            if angle_age is not None and angle_age < limits["angle_minutes"] * 60:
                return NoveltyDecision(False, "angle_cooldown", similar_score)
        if category_age is not None and category not in HELP_CATEGORIES | {"chat", "status"}:
            needed = limits["priority_category_seconds"] if priority >= 3 else limits["category_seconds"]
            if category == "idle":
                needed = max(needed, limits["idle_seconds"])
            if category_age < needed:
                return NoveltyDecision(False, "category_cooldown", similar_score)
        if category in HELP_CATEGORIES and not direct and category_age is not None and category_age < 90:
            return NoveltyDecision(False, "category_cooldown", similar_score)
        return NoveltyDecision(True, "fresh", similar_score)


def category_for(player_text: str, event: str, spontaneous: bool) -> str:
    player = player_text.lower()
    if any(bit in player for bit in ("where ", "where do", "stuck", "go next", "which way", "map")):
        return "stuck_where_to_go"
    if any(bit in player for bit in ("how do", "how to", "help", "beat", "weak", "strategy", "control", "button", "walkthrough", "hint")):
        return "player_asks_help"
    if any(bit in player for bit in ("you suck", "shut up", "trash", "stupid", "whatever")):
        return "player_talks_back"
    mapping = {
        "death": "death", "crash": "death", "win": "win", "level_clear": "win",
        "loss": "lose_round", "lose": "lose_round", "game_over": "lose_round",
        "boss": "boss_fight", "boss_fight": "boss_fight", "near_miss": "near_miss",
        "comeback": "comeback", "idle": "idle", "menu": "idle",
        "fishing_miss": "fishing_miss", "fishing_catch_small": "fishing_catch_small",
        "fishing_catch_big": "fishing_catch_big",
        "takeover_start": "takeover_start", "takeover_win": "takeover_win",
        "takeover_fail": "takeover_fail", "coop_join": "coop_join", "coop_carry": "coop_carry",
        "greeting_return": "greeting_return", "callback_to_past_session": "callback_to_past_session",
    }
    if event in mapping:
        return mapping[event]
    if spontaneous:
        return "idle"
    return "chat"
