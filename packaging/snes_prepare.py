"""Install the bundled RetroArch and Snes9x, then point Buddy at a test ROM.

The Windows smoke test runs this with the installed runtime\\python.exe.
The ROM is generated here. It is not inside BuddySetup.exe.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from backend.config_loader import LOCAL_PATH, ROOT, load_config
from backend.setup_flow import (
    apply_config,
    create_games_tree,
    fresh_state,
    install_default_cores,
    install_portable,
    save_state,
)
from backend.snes_test_rom import build_snes_test_rom


def main() -> int:
    bundle = ROOT / "bundled" / "RetroArch"
    pins = ROOT / "bundled" / "checksums.json"
    if not (bundle / "retroarch.exe").is_file():
        print("Bundled retroarch.exe is missing", file=sys.stderr)
        return 1
    checksums = json.loads(pins.read_text(encoding="utf-8-sig")) if pins.is_file() else {}
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    dest = Path(base) / "Buddy" / "RetroArch"
    error = install_portable(bundle, dest, checksums, lambda *_args: None)
    if error:
        print(error, file=sys.stderr)
        return 1
    installed, skipped, core_error = install_default_cores(
        bundle / "cores", dest / "cores", checksums, lambda *_args: None,
    )
    if core_error:
        print(core_error, file=sys.stderr)
        return 1
    core = dest / "cores" / "snes9x_libretro.dll"
    if not core.is_file() or "snes9x_libretro.dll" not in installed:
        print(f"Snes9x was not installed. installed={installed} skipped={skipped}", file=sys.stderr)
        return 1
    games = Path.home() / "Buddy Games"
    create_games_tree(games)
    rom = games / "SNES" / "buddy-snes-test.sfc"
    rom.write_bytes(build_snes_test_rom())
    state = fresh_state()
    state.update({
        "step": "done",
        "completed": False,
        "retroarch_path": str(dest / "retroarch.exe"),
        "cores_installed": installed,
        "cores_skipped": skipped,
        "games_dir": str(games),
        "scan": {"nes": [], "snes": [rom.name], "genesis": []},
        "frames": {"snes": "snes"},
        "personality": "sassy",
        "character": "male",
    })
    save_state(state)
    config = load_config(LOCAL_PATH if LOCAL_PATH.exists() else None)
    apply_config(config, state)
    config.data.setdefault("retroarch", {})["path"] = str(dest / "retroarch.exe")
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_PATH.write_text(json.dumps(config.data, indent=2) + "\n", encoding="utf-8")
    print(f"retroarch {dest / 'retroarch.exe'}")
    print(f"core {core}")
    print(f"rom {rom}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
