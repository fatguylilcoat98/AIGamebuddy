"""Keep a native library crash inside a short-lived process.

An access violation in ctranslate2, PortAudio, miniaudio, or mss kills the
whole interpreter. Probing and running those pieces in a child process turns
that into a logged failure and leaves Buddy up.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("buddy.native")

_STATUS: dict[str, str] = {}


def python_exe() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        sibling = exe.with_name("python.exe")
        if sibling.is_file():
            return str(sibling)
    return str(exe)


def crashed(code: int | None) -> bool:
    if code is None:
        return True
    if code < 0:
        return True
    # 0xC0000005 and the other NTSTATUS fatal codes show up as large unsigned values.
    return code >= 0xC0000000


def probe(name: str, statement: str, timeout: float = 25) -> str:
    """'ok', 'unavailable', or 'crashed'. The result is remembered."""
    if name in _STATUS:
        return _STATUS[name]
    code = (
        "import faulthandler, sys\n"
        "faulthandler.enable(all_threads=True)\n"
        f"{statement}\n"
        "print('ok')\n"
    )
    try:
        done = subprocess.run(
            [python_exe(), "-c", code],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _STATUS[name] = "crashed"
        log.warning("%s is off. It did not finish loading. %s", _plain(name), exc)
        return _STATUS[name]
    if done.returncode == 0 and "ok" in (done.stdout or ""):
        _STATUS[name] = "ok"
        log.info("native %s=ok", name)
        return "ok"
    if crashed(done.returncode):
        _STATUS[name] = "crashed"
        detail = ((done.stderr or "") + (done.stdout or "")).strip()
        log.warning("%s is off. The library crashed while loading (code %s). %s",
                    _plain(name), done.returncode, detail[-400:])
        return "crashed"
    _STATUS[name] = "unavailable"
    detail = ((done.stderr or "") + (done.stdout or "")).strip()
    log.info("native %s=unavailable %s", name, detail[-300:])
    return "unavailable"


def mark(name: str, status: str) -> None:
    _STATUS[name] = status


def status(name: str) -> str:
    return _STATUS.get(name, "")


def _plain(name: str) -> str:
    return {
        "microphone": "Microphone",
        "whisper": "Speech recognition",
        "audio": "Neural voice",
        "capture": "Screen capture",
    }.get(name, name)
