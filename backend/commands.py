"""Deterministic phrases that map to application actions, not model guesses."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .personality_pack import normalize_personality


@dataclass(frozen=True)
class Intent:
    name: str
    args: dict


def normalize_utterance(text: str) -> str:
    cleaned = text.lower().replace("'", "")
    cleaned = re.sub(r"\b(hey|ok|okay|please|buddy)\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def match_intent(text: str) -> Intent | None:
    norm = normalize_utterance(text)
    if not norm:
        return None
    patterns: list[tuple[str, str]] = [
        (r"^(stop insulting me|stop roasting me|stop roasting|be nice|no more insults|dont insult me|do not insult me)$", "stop_insults"),
        (r"^(you can roast me|insults ok|roasting ok|you can insult me)$", "allow_insults"),
        (r"^(mute|mute yourself|be quiet)$", "mute"),
        (r"^(unmute|unmute yourself|talk again)$", "unmute"),
        (r"^volume (\d{1,3})$", "volume_set"),
        (r"^volume (up|down)$", "volume_step"),
        (r"^(stop talking|hush|quiet|stop talking for a minute|quiet for a minute)$", "silence"),
        (r"^commentary (off|rare|normal|chatty|down|up)$", "frequency"),
        (r"^(turn the commentary down|commentary down)$", "frequency_down"),
        (r"^(turn the commentary up|commentary up)$", "frequency_up"),
        (r"^(compact layout|streaming layout|compact mode)$", "layout_compact"),
        (r"^(full overlay|full layout|retro overlay)$", "layout_full"),
        (r"^(purple overlay|snes overlay|switch to snes|switch to the purple overlay)$", "theme_snes"),
        (r"^(blue overlay|genesis overlay|switch to genesis|switch to the blue overlay)$", "theme_genesis"),
        (r"^(orange overlay|nes overlay|switch to nes|switch to the orange overlay)$", "theme_nes"),
        (r"^(what do you remember|show memory|view memory)$", "memory_view"),
        (r"^(reset memory|reset preferences)$", "memory_reset"),
        (r"^(clear memory|forget everything|wipe memory)$", "memory_clear"),
        (r"^(look at the game|look at this|what am i playing|what is this game)$", "observe"),
        (r"^(open retroarch|launch retroarch)$", "open_retroarch"),
        (r"^(open emulationstation|open es de|launch emulationstation)$", "open_es"),
        (r"^(open the emulator settings|open retroarch settings|open menu)$", "emulator_menu"),
        (r"^(you play|take over|takeover|your turn|you think youre so smart you play)$", "takeover"),
        (r"^(give me the controller|im playing|i am playing|stop playing|release control|hand it back)$", "release"),
        (r"^(co op|coop|player 2|join as player 2)$", "coop"),
        (r"^(character male|male|switch to male)$", "character_male"),
        (r"^(character female|female|switch to female)$", "character_female"),
        (r"^(rest left|look left|face the game|resting direction left)$", "rest_left"),
        (r"^(rest right|look right|resting direction right)$", "rest_right"),
        (r"^(rest center|face center|face me|resting direction center)$", "rest_center"),
    ]
    for pattern, name in patterns:
        match = re.match(pattern, norm)
        if not match:
            continue
        if name == "volume_set":
            return Intent(name, {"level": int(match.group(1))})
        if name == "volume_step":
            return Intent(name, {"direction": match.group(1)})
        if name == "frequency":
            word = match.group(1)
            mapped = {"down": "rare", "up": "chatty"}.get(word, word)
            return Intent("frequency", {"level": mapped})
        if name == "frequency_down":
            return Intent("frequency", {"level": "rare"})
        if name == "frequency_up":
            return Intent("frequency", {"level": "chatty"})
        return Intent(name, {})

    persona = re.match(r"^(?:switch to|set personality|personality|be|go) (casual|sassy|extreme|regular)$", norm)
    if persona:
        return Intent("personality", {"name": persona.group(1)})
    load = re.match(r"^(?:load|launch|start|play) (.+)$", norm)
    if load and load.group(1) not in {"retroarch", "emulationstation"}:
        return Intent("load_game", {"query": load.group(1)})
    find = re.match(r"^(?:find|search) (.+)$", norm)
    if find:
        return Intent("find_game", {"query": find.group(1)})
    return None


def personality_or_none(name: str) -> str | None:
    try:
        return normalize_personality(name)
    except ValueError:
        return None
