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
    last = _last_angle(memory, category)
    if last in angles and len(angles) > 1:
        start = angles.index(last) + 1
        angles = angles[start:] + angles[:start]
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


def _last_angle(memory: MemoryStore, category: str) -> str | None:
    for row in memory.recent_lines(80):
        if row.get("category") == category and row.get("angle"):
            return str(row["angle"])
    return None


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
                    callbacks_this_session: int, real: set[str] | None = None) -> str | None:
    """Return a line that passes the novelty gate, or None.

    Templates that can be filled come first, preferring real facts over defaults.
    Seeds are used only after those templates are blocked. Death can also draw a
    fresh counted line so a long session does not fall through to silence.
    """
    seed_lines = [line.strip() for line in pack.seeds.get(category, []) if line.strip()]
    seed_keys = {line.lower() for line in seed_lines}
    known = real if real is not None else set(slots)
    candidates: list[str] = []
    for template in _candidate_order(pack.templates.get(category, []), slots, known):
        filled = fill_template(template, slots)
        if not filled or filled.strip().lower() in seed_keys:
            continue
        candidates.append(filled)
    candidates.extend(seed_lines)
    if category == "death":
        try:
            count = int(slots.get("count") or 0)
        except ValueError:
            count = 0
        candidates.extend(fresh_death_lines(count or None))
    seen: set[str] = set()
    for filled in candidates:
        key = filled.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        decision = novelty.screen(
            filled, category=category, angle=angle, personality=personality, now=now,
            direct=direct, allow_callback=allow_callback, priority=priority,
            callbacks_this_session=callbacks_this_session, frequency=frequency,
        )
        if decision.allow:
            return filled
    return None


# Used only when a template blank has no real fact. These are generic, not guesses
# about the screen. Count is never invented.
DEFAULT_SLOTS = {
    "cause": "that hit",
    "enemy": "that enemy",
    "tell": "the windup",
    "tip": "watch the timing and try once more",
    "action": "that last move",
    "boss": "the boss",
    "timing": "the timing",
    "item": "the item you need",
    "phase": "this phase",
    "game": "this game",
    "move": "that move",
    "spacing": "your spacing",
    "deficit": "behind",
    "topic": "that",
    "section": "that section",
    "side": "the other side",
    "wave": "this wave",
    "objective": "the objective",
    "fish": "that fish",
    "lure": "the same lure",
    "last_session_event": "the last attempt",
    "direction": "ahead",
    "landmark": "the next landmark",
    "gate": "the gate",
}

# Long clauses so successive death lines stay under the similarity gate.
_DEATH_OPEN = (
    "The pit on the left opened under a greedy jump.",
    "A diving bat clipped the high arc.",
    "The knight thrust one step farther than it looked.",
    "The rolling boulder started on a late beat.",
    "The fireball arc shaved the tall hop.",
    "The conveyor dragged the landing into the saw.",
    "The ceiling drop punished a held button.",
    "The spike floor blinked and then rose.",
    "The shield bash caught a forward mash.",
    "The lava bubble popped on the tile you chose.",
    "The swinging blade returned early.",
    "The crumbling ledge gave one step and no more.",
)
_DEATH_FIX = (
    "Next life, wait for the flash and then move.",
    "Stand one tile back and tap the jump.",
    "Hold block until the weapon retracts.",
    "Jump on the second bounce, not the first.",
    "Stay low and slide under the arc.",
    "Hop against the belt before the edge.",
    "Release the button when the shadow lands.",
    "Step off the marked tile before it lifts.",
    "Stop mashing and punish the recovery.",
    "Leave that tile and take the side path.",
    "Duck the return swing and then advance.",
    "Do not chase the coin on a breaking floor.",
)


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


def complete_slots(slots: dict[str, str], pack: PersonalityPack) -> tuple[dict[str, str], set[str]]:
    """Fill every template blank. Real facts stay real. Unknown blanks get a default.

    Count is left blank when we do not have one. Returns the filled map and the
    set of keys that came from real facts.
    """
    real = {key for key, value in slots.items() if str(value).strip()}
    filled = dict(slots)
    needed: set[str] = set()
    for lines in pack.templates.values():
        for line in lines:
            needed.update(placeholders(line))
    for name in needed:
        if str(filled.get(name) or "").strip():
            continue
        if name == "count":
            continue
        filled[name] = DEFAULT_SLOTS.get(name, "that")
    return filled, real


def _candidate_order(templates: list[str], slots: dict[str, str], real: set[str]) -> list[str]:
    """Prefer templates whose blanks are real facts over ones that need defaults."""
    ranked = []
    for index, template in enumerate(templates):
        names = placeholders(template)
        if any(not str(slots.get(name) or "").strip() for name in names):
            continue
        invented = sum(1 for name in names if name not in real)
        ranked.append((invented, index, template))
    ranked.sort()
    return [template for _invented, _index, template in ranked]


def fresh_death_lines(count: int | None) -> list[str]:
    shown = str(count) if count and count > 0 else "another"
    lines = []
    for opening in _DEATH_OPEN:
        for fix in _DEATH_FIX:
            lines.append(f"Death {shown}. {opening} {fix}")
    return lines


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
