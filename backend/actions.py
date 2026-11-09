"""Real launcher and library actions. They report the process result, not a guess."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .results import ActionResult

ROM_SUFFIXES = {
    ".nes", ".fds", ".unf", ".sfc", ".smc", ".fig", ".md", ".gen", ".smd", ".bin",
    ".zip", ".7z", ".gb", ".gbc", ".gba", ".n64", ".z64", ".cue", ".iso",
}


def search_games(libraries: list[dict], query: str) -> ActionResult:
    needle = " ".join((query or "").lower().split())
    if len(needle) < 3:
        return ActionResult(False, "That search is too short, so I did not scan the library.", reason="query_short")
    if not libraries:
        return ActionResult(False, "No game library folders are configured, so I did not search.", reason="no_library")
    matches: list[str] = []
    missing: list[str] = []
    for entry in libraries:
        folder = Path(str(entry.get("path") or "")).expanduser()
        if not folder.exists() or not folder.is_dir():
            missing.append(str(folder))
            continue
        for dirpath, _dirs, files in os.walk(folder):
            for name in files:
                if Path(name).suffix.lower() not in ROM_SUFFIXES:
                    continue
                if needle in name.lower():
                    matches.append(str(Path(dirpath) / name))
                    if len(matches) >= 20:
                        break
            if len(matches) >= 20:
                break
    if missing and not matches:
        return ActionResult(False, "I did not find a game. These library folders are missing: " + "; ".join(missing),
                            reason="library_missing", data={"missing": missing})
    if not matches:
        return ActionResult(False, f"I looked in the configured libraries and did not find '{query}'.",
                            reason="not_found")
    if len(matches) > 1:
        preview = "\n".join(matches[:8])
        return ActionResult(False, f"I found {len(matches)} matches, so I did not launch one.\n{preview}",
                            reason="ambiguous", data={"matches": matches})
    return ActionResult(True, f"Found {matches[0]}.", reason="found", data={"matches": matches})


def launch_process(path: str, args: list[str] | None = None, runner=None) -> ActionResult:
    if not str(path or "").strip():
        return ActionResult(False, "No program path is configured, so I did not launch anything.", reason="no_path")
    program = Path(path).expanduser()
    if not program.exists():
        return ActionResult(False, f"I did not launch it. That path does not exist: {program}", reason="missing_path")
    command = [str(program), *(args or [])]
    try:
        if runner is None:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pid = proc.pid
        else:
            pid = runner(command)
    except OSError as exc:
        return ActionResult(False, f"I did not launch it. {exc}", reason="launch_failed")
    return ActionResult(True, f"Started process {pid}.", reason="launched", data={"pid": pid, "command": command})
