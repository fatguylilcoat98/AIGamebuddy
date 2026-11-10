# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows Buddy Overlay bundle."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

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
]

for pkg in (
    "sounddevice",
    "_sounddevice_data",
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "onnxruntime",
    "av",
    "huggingface_hub",
):
    try:
        collected_datas, collected_binaries, collected_hidden = collect_all(pkg)
        datas += collected_datas
        binaries += collected_binaries
        hiddenimports += collected_hidden
    except Exception:
        try:
            datas += collect_data_files(pkg)
        except Exception:
            pass
        try:
            binaries += collect_dynamic_libs(pkg)
        except Exception:
            pass

a = Analysis(
    [str(ROOT / "packaging" / "buddy_entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
