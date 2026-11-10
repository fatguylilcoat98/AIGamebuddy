"""Save states for games that have none of their own.

RetroArch writes the files. Buddy keeps them in its data folder, per game,
so an upgrade of the app does not delete them. Slot 0 is the automatic
continue spot. Slots 1, 2, and 3 are the ones in the menu.

RetroArch 1.22 can load a numbered slot directly. Saving still uses the
current slot, so a save walks back to slot 0 and then up to the slot we want
before SAVE_STATE.
"""
from __future__ import annotations

import json
from pathlib import Path

MANUAL_SLOTS = (1, 2, 3)
AUTO_SLOT = 0


def save_commands(slot: int) -> list[str]:
    """Commands that land on `slot` and save, whatever the previous slot was."""
    slot = int(slot)
    if slot < 0:
        slot = 0
    # Minus clamps at 0. Sixteen steps is enough to leave any normal slot.
    commands = ["STATE_SLOT_MINUS"] * 16
    commands.extend(["STATE_SLOT_PLUS"] * slot)
    commands.append("SAVE_STATE")
    return commands


def load_commands(slot: int) -> list[str]:
    return [f"LOAD_STATE_SLOT {int(slot)}"]


def state_directory(data_dir: Path) -> Path:
    path = Path(data_dir) / "savestates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_lines(directory: Path, *, auto_load: bool) -> list[str]:
    folder = Path(directory).as_posix()
    return [
        f'savestate_directory = "{folder}"',
        'savestates_in_content_dir = "false"',
        'sort_savestates_enable = "true"',
        'savestate_auto_index = "false"',
        'savestate_auto_save = "false"',
        f'savestate_auto_load = "{"true" if auto_load else "false"}"',
        'state_slot = "0"',
    ]


def _index_path(directory: Path) -> Path:
    return Path(directory) / "index.json"


def _load_index(directory: Path) -> dict:
    path = _index_path(directory)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def remember_save(directory: Path, rom: str, slot: int) -> None:
    """Remember which game owns this slot. The state file itself is RetroArch's."""
    rom = str(rom or "").strip()
    if not rom:
        return
    data = _load_index(directory)
    games = data.setdefault("games", {})
    if not isinstance(games, dict):
        games = {}
        data["games"] = games
    entry = games.setdefault(rom, {})
    if not isinstance(entry, dict):
        entry = {}
        games[rom] = entry
    entry[str(int(slot))] = True
    path = _index_path(directory)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def has_slot(directory: Path, rom: str, slot: int) -> bool:
    data = _load_index(directory)
    games = data.get("games") or {}
    entry = games.get(str(rom)) or {}
    return bool(isinstance(entry, dict) and entry.get(str(int(slot))))


def has_continue(directory: Path, rom: str) -> bool:
    return has_slot(directory, rom, AUTO_SLOT)


def save_line(personality: str, slot: int) -> str:
    if slot == AUTO_SLOT:
        return "I saved your spot, so you can continue later."
    if personality == "extreme":
        return f"Saved. Slot {slot}. Don't lose it."
    if personality == "casual":
        return f"Saved. Slot {slot} has your spot."
    return f"Got it. Slot {slot} is holding your place."


def load_line(slot: int) -> str:
    if slot == AUTO_SLOT:
        return "Back to where you left off."
    return f"Back to slot {slot}."
