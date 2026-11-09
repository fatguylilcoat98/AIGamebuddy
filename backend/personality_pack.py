"""Load writer-supplied personality packs.

Each mode folder has:
  STYLE.md          voice guide, included in the model prompt
  seeds.json        style examples by category. Never spoken verbatim.
  templates.json    fill-in shapes for a fresh line when the slots are real facts.

Angle lists and cooldowns come from data/personalities/ANTI-REPETITION.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data" / "personalities"
RULES_PATH = PACK_ROOT / "ANTI-REPETITION.md"

ALIASES = {"regular": "casual", "friendly": "casual"}
MODES = ("casual", "sassy", "extreme")

# Cooldowns from ANTI-REPETITION.md. Angle and category use the long end of
# each suggested range so a heavy player does not hear the same bit twice.
COOLDOWNS = {
    "casual": {"exact_hours": 72, "angle_minutes": 90, "category_seconds": 180,
               "priority_category_seconds": 90, "metaphor_hours": 24, "idle_seconds": 600},
    "sassy": {"exact_hours": 72, "angle_minutes": 60, "category_seconds": 180,
              "priority_category_seconds": 90, "metaphor_hours": 24, "idle_seconds": 600},
    "extreme": {"exact_hours": 72, "angle_minutes": 45, "category_seconds": 180,
                "priority_category_seconds": 90, "metaphor_hours": 24, "idle_seconds": 600},
}

PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")


class PackError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class Angle:
    id: str
    note: str = ""


@dataclass
class PersonalityPack:
    id: str
    style: str
    seeds: dict[str, list[str]]
    templates: dict[str, list[str]]
    path: Path
    angles: dict[str, list[Angle]] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.id.title()

    def style_examples(self, category: str, limit: int = 2) -> list[str]:
        return list(self.seeds.get(category, [])[:limit])

    def template_examples(self, category: str, limit: int = 2) -> list[str]:
        return list(self.templates.get(category, [])[:limit])


def normalize_personality(name: str) -> str:
    cleaned = (name or "").strip().lower()
    cleaned = ALIASES.get(cleaned, cleaned)
    if cleaned not in MODES:
        raise ValueError(f"personality must be one of: {', '.join(MODES)} (regular means casual)")
    return cleaned


def parse_angles(text: str) -> dict[str, list[Angle]]:
    """Read the per-category angle lists out of ANTI-REPETITION.md."""
    angles: dict[str, list[Angle]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = re.match(r"^###\s+([a-z0-9_]+)\s*$", line.strip())
        if heading:
            current = heading.group(1)
            angles[current] = []
            continue
        if current is None:
            continue
        if line.strip().startswith("- `"):
            found = re.findall(r"`([a-z0-9_]+)`", line)
            note = line.split("—", 1)[1].strip() if "—" in line else ""
            for angle_id in found:
                angles[current].append(Angle(angle_id, note if len(found) == 1 else note))
    return angles


def load_angles(path: Path | None = None) -> dict[str, list[Angle]]:
    rules = path or RULES_PATH
    if not rules.exists():
        raise PackError([f"Missing anti-repetition rules: {rules}"])
    return parse_angles(rules.read_text(encoding="utf-8"))


def _read_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"{path.name} is not valid JSON ({exc.lineno}:{exc.colno})"
    if not isinstance(data, dict):
        return None, f"{path.name} must be an object of category -> list of lines"
    return data, None


def validate_mode(folder: Path, angles: dict[str, list[Angle]]) -> list[str]:
    errors: list[str] = []
    style_path = folder / "STYLE.md"
    seeds_path = folder / "seeds.json"
    templates_path = folder / "templates.json"
    if not style_path.exists():
        errors.append(f"{folder.name}: missing STYLE.md")
        style = ""
    else:
        style = style_path.read_text(encoding="utf-8")
        if len(style.strip()) < 200:
            errors.append(f"{folder.name}: STYLE.md is too short to be a voice guide")
        for heading in ("Voice", "Attitude", "Vocabulary", "NEVER"):
            if heading not in style:
                errors.append(f"{folder.name}: STYLE.md is missing a {heading} section")
    seeds, problem = (None, f"{folder.name}: missing seeds.json") if not seeds_path.exists() else _read_json(seeds_path)
    if problem:
        errors.append(f"{folder.name}: {problem}")
    templates, problem = (None, f"{folder.name}: missing templates.json") if not templates_path.exists() else _read_json(templates_path)
    if problem:
        errors.append(f"{folder.name}: {problem}")
    if seeds is None or templates is None or not angles:
        return errors
    if set(seeds) != set(angles):
        missing = sorted(set(angles) - set(seeds))
        extra = sorted(set(seeds) - set(angles))
        if missing:
            errors.append(f"{folder.name}: seeds.json missing categories {missing}")
        if extra:
            errors.append(f"{folder.name}: seeds.json has unknown categories {extra}")
    if set(templates) != set(angles):
        missing = sorted(set(angles) - set(templates))
        extra = sorted(set(templates) - set(angles))
        if missing:
            errors.append(f"{folder.name}: templates.json missing categories {missing}")
        if extra:
            errors.append(f"{folder.name}: templates.json has unknown categories {extra}")
    seed_total = 0
    for category, expected in angles.items():
        rows = seeds.get(category)
        if not isinstance(rows, list) or len(rows) < 8:
            errors.append(f"{folder.name}: seeds[{category}] needs at least 8 example lines")
            continue
        seed_total += len(rows)
        if any(not isinstance(line, str) or not line.strip() for line in rows):
            errors.append(f"{folder.name}: seeds[{category}] contains an empty line")
        shaped = templates.get(category)
        if not isinstance(shaped, list) or not shaped:
            errors.append(f"{folder.name}: templates[{category}] needs at least one template")
            continue
        if any(not isinstance(line, str) or not line.strip() for line in shaped):
            errors.append(f"{folder.name}: templates[{category}] contains an empty line")
        if not expected:
            errors.append(f"{folder.name}: angle list for {category} is empty")
    if seed_total < 200:
        errors.append(f"{folder.name}: expected a full seed pack, found {seed_total} lines")
    if "zion" in style.lower():
        errors.append(f"{folder.name}: STYLE.md must not name the character Zion")
    return errors


def validate_tree(root: Path | None = None) -> list[str]:
    base = root or PACK_ROOT
    errors: list[str] = []
    rules = base / "ANTI-REPETITION.md"
    if not rules.exists():
        return [f"Missing {rules}"]
    angles = parse_angles(rules.read_text(encoding="utf-8"))
    if len(angles) < 20:
        errors.append(f"Expected 20 angle categories, found {sorted(angles)}")
    for mode in MODES:
        errors.extend(validate_mode(base / mode, angles))
    return errors


def load_pack(name: str, root: Path | None = None) -> PersonalityPack:
    pack_id = normalize_personality(name)
    base = root or PACK_ROOT
    angles = load_angles(base / "ANTI-REPETITION.md")
    folder = base / pack_id
    errors = validate_mode(folder, angles)
    if errors:
        raise PackError(errors)
    seeds, _ = _read_json(folder / "seeds.json")
    templates, _ = _read_json(folder / "templates.json")
    assert seeds is not None and templates is not None
    return PersonalityPack(
        id=pack_id,
        style=folder.joinpath("STYLE.md").read_text(encoding="utf-8"),
        seeds={key: list(value) for key, value in seeds.items()},
        templates={key: list(value) for key, value in templates.items()},
        path=folder,
        angles=angles,
    )


def placeholders(template: str) -> list[str]:
    return PLACEHOLDER.findall(template)
