"""Import check for the installed runtime only. Run it from another directory.

The embeddable interpreter must see backend via python312._pth (`..`) and must
have its own tkinter. A system Python is not used.
"""
from __future__ import annotations

import importlib
import pkgutil
import tkinter

import backend

REQUIRED = (
    "PIL.ImageTk",
    "numpy",
    "edge_tts",
    "uvicorn",
    "fastapi",
    "mss",
    "sounddevice",
    "miniaudio",
    "faster_whisper",
)

failed: list[str] = []
names = [module.name for module in pkgutil.walk_packages(backend.__path__, prefix="backend.")]
for name in names:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failed.append(f"{name}: {type(exc).__name__}: {exc}")
for name in REQUIRED:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failed.append(f"{name}: {type(exc).__name__}: {exc}")

root = tkinter.Tk()
patch = root.tk.call("info", "patchlevel")
root.update_idletasks()
root.destroy()
print(f"tk {patch}")
print(f"backend-modules {len(names)}")
if failed:
    print("\n".join(failed))
    raise SystemExit(1)
print("imports-ok")
