# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows Buddy Overlay bundle.

Native libraries are collected explicitly. A missing PortAudio DLL or
ctranslate2 binary fails the build instead of shipping a broken exe.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "config"), "config"),
    (str(ROOT / "data"), "data"),
    (str(ROOT / "LICENSES.md"), "."),
]
binaries = []
hiddenimports = [
    "backend.launcher",
    "backend.main",
    "backend.buddy_api",
    "backend.app_state",
    "backend.buddy_ears",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "PIL._tkinter_finder",
    "tkinter",
    "tkinter.filedialog",
    "_cffi_backend",
    "faster_whisper",
    "faster_whisper.audio",
    "faster_whisper.feature_extractor",
    "faster_whisper.tokenizer",
    "faster_whisper.vad",
    "ctranslate2",
    "tokenizers",
    "onnxruntime",
    "sounddevice",
    "_sounddevice",
    "_sounddevice_data",
    "huggingface_hub",
    "hf_xet",
    "numpy",
    "mss",
]


def _skip_torch_converters(name: str) -> bool:
    # ctranslate2.converters and ctranslate2.specs import torch. Buddy only runs inference.
    blocked = ("ctranslate2.converters", "ctranslate2.specs")
    return not name.startswith(blocked)


def _collect(package: str, *, submodules: bool = True, filter_name=None) -> None:
    try:
        datas.extend(collect_data_files(package))
        binaries.extend(collect_dynamic_libs(package))
        if submodules:
            hiddenimports.extend(
                collect_submodules(package, filter=filter_name or (lambda _name: True), on_error="ignore")
            )
    except Exception as exc:
        raise SystemExit(f"Could not collect {package} for the Buddy bundle: {exc}") from exc


for package in (
    "sounddevice",
    "_sounddevice_data",
    "faster_whisper",
    "tokenizers",
    "onnxruntime",
    "huggingface_hub",
    "hf_xet",
):
    _collect(package)

_collect("ctranslate2", filter_name=_skip_torch_converters)

# av.libs must stay in that directory. Collecting those DLLs as binaries makes
# PyInstaller flatten a second copy and breaks av's loader.
hiddenimports.extend(collect_submodules("av", on_error="ignore"))
datas.extend(collect_data_files("av"))
try:
    import av
except Exception as exc:
    raise SystemExit(f"av is required to bundle Buddy: {exc}") from exc
av_libs = Path(av.__file__).resolve().parent.parent / "av.libs"
if av_libs.is_dir():
    for entry in av_libs.iterdir():
        if entry.is_file():
            datas.append((str(entry), "av.libs"))
elif sys.platform == "win32":
    raise SystemExit("av.libs was not found; faster-whisper cannot decode audio")

# sounddevice loads this exact relative path from _sounddevice_data.__path__.
try:
    import sounddevice
except Exception as exc:
    raise SystemExit(f"sounddevice is required to bundle Buddy: {exc}") from exc
_sounddevice_anchor = Path(sounddevice.__file__).resolve().parent
portaudio_dir = None
for candidate in (
    _sounddevice_anchor / "_sounddevice_data" / "portaudio-binaries",
    _sounddevice_anchor.parent / "_sounddevice_data" / "portaudio-binaries",
):
    if candidate.is_dir():
        portaudio_dir = candidate
        break
if portaudio_dir is not None:
    for lib in portaudio_dir.glob("libportaudio*"):
        if lib.suffix.lower() in {".dll", ".dylib", ".so"}:
            binaries.append((str(lib), "_sounddevice_data/portaudio-binaries"))
elif sys.platform == "win32":
    raise SystemExit("sounddevice PortAudio binaries were not found")

collected_names = " ".join(Path(src).name.lower() for src, _dest in binaries + datas)
missing = []
if "portaudio" not in collected_names:
    missing.append("PortAudio library")
if "ctranslate2" not in collected_names:
    missing.append("ctranslate2 binary")
if "silero" not in collected_names:
    missing.append("silero VAD model")
if sys.platform == "win32" and "avcodec" not in collected_names:
    missing.append("avcodec DLL")
if missing:
    preview = "\n".join(f"{src} -> {dest}" for src, dest in (binaries + datas)[:40])
    raise SystemExit("Buddy bundle is missing: " + ", ".join(missing) + "\n" + preview)

a = Analysis(
    [str(ROOT / "packaging" / "buddy_entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "transformers"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Buddy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Buddy",
)
