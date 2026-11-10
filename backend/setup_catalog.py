"""Pinned install pieces and which cores Buddy is allowed to ship.

The setup offers Super NES only: Snes9x and the SNES frame. NES and Genesis
stay in this list so the rest of Buddy can still name them. They are not installed.
"""
from __future__ import annotations

from dataclasses import dataclass


RETROARCH_VERSION = "1.22.1"
PYTHON_VERSION = "3.12.8"

# Checksums stay empty until packaging/build-windows.ps1 pins them.
# An empty checksum means the wizard refuses the download.
ARTIFACTS = [
    {
        "id": "retroarch",
        "name": "RetroArch",
        "version": RETROARCH_VERSION,
        "url": "https://buildbot.libretro.com/stable/1.22.1/windows/x86_64/RetroArch.7z",
        "filename": "RetroArch.7z",
        "sha256": "",
    },
    {
        "id": "python",
        "name": "Python runtime",
        "version": PYTHON_VERSION,
        "url": "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip",
        "filename": "python-3.12.8-embed-amd64.zip",
        "sha256": "",
    },
    {
        "id": "vcredist",
        "name": "Visual C++ runtime",
        "version": "2022",
        "url": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
        "filename": "vc_redist.x64.exe",
        "sha256": "",
    },
]


@dataclass(frozen=True)
class CoreSpec:
    system: str
    name: str
    filename: str
    license: str
    commercial_ok: bool
    default: bool
    note: str


CORES = (
    CoreSpec(
        "nes", "FCEUmm", "fceumm_libretro.dll", "GPL-2.0-only", True, True,
        "NES core. Left in the catalog. Not installed while Buddy is Super NES only.",
    ),
    CoreSpec(
        "nes", "Mesen", "mesen_libretro.dll", "GPL-3.0-or-later", True, False,
        "Optional NES core. Not installed.",
    ),
    CoreSpec(
        "snes", "Snes9x", "snes9x_libretro.dll", "Non-commercial", True, True,
        "Super NES core Chris asked for. Personal use. Not for sale until the rights are cleared.",
    ),
    CoreSpec(
        "snes", "bsnes", "bsnes_libretro.dll", "GPL-3.0-or-later", True, False,
        "GPL Super NES core. Left in the catalog. Not installed while Snes9x is the one Buddy sets up.",
    ),
    CoreSpec(
        "genesis", "BlastEm", "blastem_libretro.dll", "GPL-3.0-or-later", True, True,
        "Genesis core. Left in the catalog. Not installed while Buddy is Super NES only.",
    ),
    CoreSpec(
        "genesis", "PicoDrive", "picodrive_libretro.dll", "Non-commercial", False, False,
        "Libretro lists PicoDrive as non-commercial. Not installed.",
    ),
    CoreSpec(
        "genesis", "Genesis Plus GX", "genesis_plus_gx_libretro.dll", "Non-commercial", False, False,
        "The license forbids selling it or using it in a commercial product. Not installed.",
    ),
)

SYSTEM_FOLDERS = {"nes": "NES", "snes": "SNES", "genesis": "Genesis"}
SYSTEM_LABELS = {"nes": "NES", "snes": "Super NES", "genesis": "Genesis"}
# What the wizard offers right now. The other systems stay in the code.
OFFERED_SYSTEMS = ("snes",)
FRAME_CHOICES = (
    ("snes", "SNES sky kingdom"),
)
ALL_FRAME_CHOICES = (
    ("genesis", "Genesis 16-bit"),
    ("nes", "NES 8-bit dungeon"),
    ("snes", "SNES sky kingdom"),
)


def default_cores() -> tuple[CoreSpec, ...]:
    return tuple(
        core for core in CORES
        if core.default and core.commercial_ok and core.system in OFFERED_SYSTEMS
    )


def blocked_cores() -> tuple[CoreSpec, ...]:
    return tuple(core for core in CORES if not core.commercial_ok)


def cores_not_installed() -> tuple[CoreSpec, ...]:
    """Cores the wizard does not copy in. Includes NES, Genesis, and blocked licenses."""
    shipped = {core.filename for core in default_cores()}
    return tuple(core for core in CORES if core.filename not in shipped)


def offered_folders() -> dict[str, str]:
    return {key: value for key, value in SYSTEM_FOLDERS.items() if key in OFFERED_SYSTEMS}


def default_core_filename(system: str) -> str:
    for core in default_cores():
        if core.system == system:
            return core.filename
    return ""


def core_by_filename(filename: str) -> CoreSpec | None:
    for core in CORES:
        if core.filename == filename:
            return core
    return None
