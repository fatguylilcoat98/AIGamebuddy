"""Stop Buddy, the game, or every Buddy process.

Exit to desktop has to leave nothing running: RetroArch, the overlay, and
the Python process that started them. The match is the install folder and
Buddy's own modules, so an unrelated Python on the machine is left alone.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def is_buddy_process(command: str, exe: str = "") -> bool:
    """True for Buddy's Python, its wizard, or a RetroArch Buddy launched."""
    text = f"{command or ''} {exe or ''}".replace("/", "\\").lower()
    if "\\buddy\\runtime\\python.exe" in text:
        return True
    if "backend.launcher" in text or "backend.wizard_app" in text or "backend.overlay_app" in text:
        return True
    if "retroarch.exe" in text and "\\buddy\\" in text:
        return True
    return False


def list_buddy_pids(reader=None) -> list[int]:
    """Process ids Buddy should close. `reader` yields (pid, command, exe) for tests."""
    if reader is None:
        reader = _windows_processes if os.name == "nt" else _empty_processes
    found = []
    for pid, command, exe in reader():
        if pid and is_buddy_process(command, exe):
            found.append(int(pid))
    return found


def _empty_processes():
    return []


def _windows_processes():
    try:
        import csv
        import io
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine,ExecutablePath | ConvertTo-Csv -NoTypeInformation"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows = []
    try:
        for row in csv.DictReader(io.StringIO(completed.stdout or "")):
            pid = int(row.get("ProcessId") or 0)
            rows.append((pid, row.get("CommandLine") or "", row.get("ExecutablePath") or ""))
    except (ValueError, csv.Error):
        return []
    return rows


def kill_pids(pids: list[int], runner=None) -> None:
    if os.name != "nt":
        return
    launch = runner or subprocess.Popen
    for pid in pids:
        if not pid or int(pid) == os.getpid():
            continue
        try:
            launch(
                ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            continue


def install_root() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    root = Path(local) / "Buddy"
    return root if root.is_dir() else None
