"""Pick a fresh angle and build a line without playing the seed library.

Seeds are shown to the model as style examples. Templates are spoken only when
every blank can be filled with a fact we already have. Otherwise Buddy stays quiet.
"""
from __future__ import annotations

import re

from .memory_store import MemoryStore
from .novelty import NoveltyEngine
from .personality_pack import PersonalityPack, placeholders

INSULTS = re.compile(r"\b(fuck|fucking|shit|suck|crap|asshole|bitch|dumbass|idiot)\b", re.IGNORECASE)


def insults_player(text: str) -> bool:
    return bool(INSULTS.search(text or ""))


def select_angle(pack: PersonalityPack, memory: MemoryStore, category: str, now: float,
                 novelty: NoveltyEngine, *, personality: str, priority: int = 1,
                 frequency: str = "normal") -> str | None:
    angles = [item.id for item in pack.angles.get(category, [])]
    if not angles:
        return None
    available = []
    for angle in angles:
        probe = novelty.screen(
            f"angle probe {angle}",
            category=category,
            angle=angle,
            personality=personality,
            now=now,
            priority=priority,
            frequency=frequency,
        )
        # The probe text is unique, so similarity should not be why it fails.
        if probe.allow or probe.reason == "too_similar":
            # Re-check angle rules with an empty-similar sentence that cannot match history.
            decision = novelty.screen(
                f"zzq {category} {angle} {int(now)}",
                category=category,
                angle=angle,
                personality=personality,
                now=now,
                priority=priority,
                frequency=frequency,
            )
            if decision.allow:
                available.append(angle)
    return available[0] if available else None


def fill_template(template: str, slots: dict[str, str]) -> str | None:
    names = placeholders(template)
    if not names:
        return None
    if any(not str(slots.get(name) or "").strip() for name in names):
        return None

    def repl(match: re.Match) -> str:
        return str(slots[match.group(1)]).strip()

    filled = re.sub(r"\{([a-z0-9_]+)\}", repl, template)
    filled = " ".join(filled.split())
    return filled or None


def offline_variant(pack: PersonalityPack, category: str, slots: dict[str, str],
                    novelty: NoveltyEngine, *, personality: str, angle: str, now: float,
                    priority: int, frequency: str, direct: bool, allow_callback: bool,
                    callbacks_this_session: int) -> str | None:
    """Return a filled template that passes the novelty gate, or None.

    Seed lines are never returned.
    """
    seeds = {line.strip().lower() for line in pack.seeds.get(category, [])}
    for template in pack.templates.get(category, []):
        filled = fill_template(template, slots)
        if not filled or filled.strip().lower() in seeds:
            continue
        decision = novelty.screen(
            filled, category=category, angle=angle, personality=personality, now=now,
            direct=direct, allow_callback=allow_callback, priority=priority,
            callbacks_this_session=callbacks_this_session, frequency=frequency,
        )
        if decision.allow:
            return filled
    return None


def known_slots(*, count: int | None = None, game: str | None = None,
                last_session_event: str | None = None, enemy: str | None = None,
                tip: str | None = None, cause: str | None = None, boss: str | None = None,
                direction: str | None = None) -> dict[str, str]:
    slots: dict[str, str] = {}
    if count is not None and count > 0:
        slots["count"] = str(count)
    for key, value in {
        "game": game, "last_session_event": last_session_event, "enemy": enemy,
        "tip": tip, "cause": cause, "boss": boss, "direction": direction,
    }.items():
        if value and str(value).strip():
            slots[key] = str(value).strip()
    return slots


def example_block(pack: PersonalityPack, category: str) -> str:
    seeds = pack.style_examples(category, 2)
    templates = pack.template_examples(category, 1)
    lines = ["Style examples. Do not say these words. Write a new line:"]
    lines.extend(f"- {seed}" for seed in seeds)
    if templates:
        lines.append("Shape you may follow only with known facts: " + templates[0])
    return "\n".join(lines)


def angle_note(pack: PersonalityPack, category: str, angle: str) -> str:
    for item in pack.angles.get(category, []):
        if item.id == angle:
            return item.note
    return ""
