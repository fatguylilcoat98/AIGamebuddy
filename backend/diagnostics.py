"""Startup logs Chris can read after a crash.

buddy.log is a rotating text log. crash.log is faulthandler's all-thread dump
for a native access violation, which never reaches a Python except block.
"""
from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_INSTALLED = False
_CRASH_FILE = None


def log_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(root) / "Buddy" / "logs"


def install() -> Path:
    """Arm logs once. Safe to call from the wizard and again from the overlay."""
    global _INSTALLED, _CRASH_FILE
    folder = log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if _INSTALLED:
        return folder
    _INSTALLED = True
    crash_path = folder / "crash.log"
    _CRASH_FILE = crash_path.open("a", encoding="utf-8", buffering=1)
    _CRASH_FILE.write(
        f"faulthandler armed pid={os.getpid()} python={sys.executable}\n"
    )
    _CRASH_FILE.flush()
    faulthandler.enable(file=_CRASH_FILE, all_threads=True)

    buddy_path = folder / "buddy.log"
    handler = RotatingFileHandler(
        buddy_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not any(isinstance(item, logging.StreamHandler) and not isinstance(item, RotatingFileHandler)
               for item in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(stream)

    def _thread_error(args) -> None:
        logging.getLogger("buddy.crash").error(
            "Thread %s failed", getattr(args.thread, "name", ""), exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_error
    logging.getLogger("buddy.startup").info(
        "startup logs buddy.log and crash.log in %s", folder,
    )
    return folder
