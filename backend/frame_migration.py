"""First launch after an upgrade shows the current Super NES frame.

Older builds stored a Genesis theme in the data folder. The installer does
not wipe that folder, so the old choice would come back. A revision stamp
resets the frame once, then leaves later choices alone.
"""
from __future__ import annotations

import json
from pathlib import Path

FRAME_REVISION = "snes-v11"


def migrate_saved_theme(data: dict, stamp_path: Path, revision: str = FRAME_REVISION) -> dict:
    """Return UI state that shows the Super NES frame when the stamp is old."""
    previous = ""
    if stamp_path.is_file():
        try:
            previous = stamp_path.read_text(encoding="utf-8").strip()
        except OSError:
            previous = ""
    out = dict(data or {})
    if previous == revision:
        return out
    out["theme"] = "snes"
    out["theme_mode"] = "snes"
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(revision + "\n", encoding="utf-8")
    return out


def migrate_setup_state(path: Path, revision: str = FRAME_REVISION) -> None:
    """Point a leftover setup file at the Super NES frame. Games stay put."""
    stamp = path.parent / "frame-revision.txt"
    if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == revision:
        return
    if not path.is_file():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(state, dict):
        return
    state["frames"] = {"snes": "snes"}
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    stamp.write_text(revision + "\n", encoding="utf-8")
