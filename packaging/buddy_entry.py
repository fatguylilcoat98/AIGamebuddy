"""Frozen Windows entry point. Starts Buddy Overlay."""
from __future__ import annotations

import sys
from pathlib import Path

VERSION = "0.9.0"


def _prepare_path() -> None:
    # A frozen bundle already imports from the PyInstaller archive.
    # Inserting the folder that contains Buddy.exe would shadow that.
    if getattr(sys, "frozen", False):
        return
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def self_test() -> int:
    """Import native dependencies and confirm bundled assets are visible."""
    _prepare_path()
    problems: list[str] = []
    print(f"frozen={getattr(sys, 'frozen', False)} meipass={getattr(sys, '_MEIPASS', '')}")

    from backend.config_loader import resource_root

    root = resource_root()
    print(f"resource_root={root}")
    required = [
        root / "assets" / "frames" / "metadata.json",
        root / "assets" / "frames" / "nes-8bit-dungeon.png",
        root / "assets" / "frames" / "snes-sky-kingdom.png",
        root / "assets" / "frames" / "genesis-16bit.png",
        root / "config" / "buddy.config.sample.json",
        root / "data" / "personalities" / "sassy" / "STYLE.md",
    ]
    for path in required:
        print(f"asset {path} exists={path.is_file()}")
        if not path.is_file():
            problems.append(f"missing {path}")

    try:
        import sounddevice as sd

        print("portaudio_version", sd.get_portaudio_version())
        libraries: list[Path] = []
        try:
            import _sounddevice_data
        except ImportError:
            _sounddevice_data = None
        if _sounddevice_data is not None:
            base = Path(next(iter(_sounddevice_data.__path__)))
            libraries = sorted(
                path for path in base.rglob("*portaudio*")
                if path.is_file() and path.suffix.lower() in {".dll", ".dylib", ".so"}
            )
            print("portaudio", [str(path) for path in libraries])
        # Windows wheels and the frozen app ship the DLL beside _sounddevice_data.
        # A Linux source checkout may use the system PortAudio library instead.
        if getattr(sys, "frozen", False) and not any(path.suffix.lower() == ".dll" for path in libraries):
            problems.append("PortAudio DLL was not found in the frozen bundle")
    except Exception as exc:
        problems.append(f"sounddevice: {exc}")

    try:
        import ctranslate2
        import faster_whisper
        import onnxruntime

        print("ctranslate2", getattr(ctranslate2, "__file__", ""))
        print("faster_whisper", getattr(faster_whisper, "__version__", ""))
        print("onnxruntime", getattr(onnxruntime, "__version__", ""))
    except Exception as exc:
        problems.append(f"speech: {exc}")

    if sys.platform == "win32" or getattr(sys, "frozen", False):
        try:
            import tkinter

            print("tkinter", tkinter.TkVersion)
        except Exception as exc:
            problems.append(f"tkinter: {exc}")

    try:
        import backend.launcher  # noqa: F401
        import backend.main  # noqa: F401

        print("launcher imported")
    except Exception as exc:
        problems.append(f"launcher: {exc}")

    if problems:
        print("SELF-TEST FAILED")
        for item in problems:
            print(item)
        return 1
    print("SELF-TEST OK")
    return 0


def main() -> int:
    _prepare_path()
    if "--version" in sys.argv:
        print(f"Buddy Overlay {VERSION}")
        return 0
    if "--self-test" in sys.argv:
        return self_test()
    from backend.launcher import main as launch

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
