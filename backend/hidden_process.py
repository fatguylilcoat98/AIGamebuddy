"""Start a process without a console window.

Every subprocess in backend/ goes through here. On Windows the helper sets
CREATE_NO_WINDOW and a hidden startup window, so pythonw never flashes a
console while it captures, listens, or launches RetroArch.
"""
from __future__ import annotations

import os
import subprocess


def hidden_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0  # SW_HIDE
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flags, "startupinfo": startup}


def _force_hidden(kwargs: dict) -> dict:
    merged = dict(kwargs)
    extra = hidden_kwargs()
    flags = int(merged.get("creationflags") or 0) | int(extra.get("creationflags") or 0)
    merged.update(extra)
    if flags:
        merged["creationflags"] = flags
    return merged


def run(args, **kwargs):
    return subprocess.run(args, **_force_hidden(kwargs))


def popen(args, **kwargs):
    return subprocess.Popen(args, **_force_hidden(kwargs))


def call(args, **kwargs):
    return subprocess.call(args, **_force_hidden(kwargs))


def detach_console() -> None:
    """Drop a console if a library allocated one after startup."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        return
