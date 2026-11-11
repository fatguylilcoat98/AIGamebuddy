"""Find RetroArch and describe the window that should sit in the game hole.

Path checks and the append-config text are pure so tests can run without
Windows. The overlay calls the Windows pieces after this decides what to do.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from .config_loader import SAMPLE_PATH, Config
from .frame_library import ASPECT_RATIO_CUSTOM

# Super NES is shown at 4:3. The picture fills the window on the short side.
SNES_DISPLAY_ASPECT = 4 / 3

log = logging.getLogger("buddy.retroarch")

NOTICE_LOOKING = "Looking for RetroArch"
NOTICE_MISSING = "RetroArch was not found"
NOTICE_FAILED = "RetroArch did not open"
FIND_LABEL = "Find RetroArch"


def common_exe_candidates(environ: dict | None = None) -> list[str]:
    """Install locations to try before the registry and PATH.

    The list is finite. It does not walk the disk.
    """
    env = os.environ if environ is None else environ
    program_files = env.get("ProgramFiles") or r"C:\Program Files"
    program_files_x86 = env.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    appdata = env.get("APPDATA") or ""
    local = env.get("LOCALAPPDATA") or ""
    home = env.get("USERPROFILE") or env.get("HOME") or ""
    found = [
        r"C:\RetroArch-Win64\retroarch.exe",
        r"C:\RetroArch\retroarch.exe",
        str(Path(program_files) / "RetroArch" / "retroarch.exe"),
        str(Path(program_files) / "RetroArch-Win64" / "retroarch.exe"),
        str(Path(program_files_x86) / "RetroArch" / "retroarch.exe"),
        str(Path(program_files_x86) / "RetroArch-Win64" / "retroarch.exe"),
    ]
    if appdata:
        found.append(str(Path(appdata) / "RetroArch" / "retroarch.exe"))
    if local:
        found.append(str(Path(local) / "RetroArch" / "retroarch.exe"))
    for base in (program_files_x86, program_files):
        found.append(str(Path(base) / "Steam" / "steamapps" / "common" / "RetroArch" / "retroarch.exe"))
    for drive in "CDEFG":
        root = f"{drive}:\\"
        found.append(root + r"SteamLibrary\steamapps\common\RetroArch\retroarch.exe")
        found.append(root + r"Steam\steamapps\common\RetroArch\retroarch.exe")
    if home:
        found.append(str(Path(home) / "scoop" / "apps" / "retroarch" / "current" / "retroarch.exe"))
    return found


def registry_retroarch_exes() -> list[str]:
    """Uninstall InstallLocation and App Paths. Empty when winreg is unavailable."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    found: list[str] = []
    uninstall = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in uninstall:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            count = winreg.QueryInfoKey(key)[0]
            for index in range(count):
                try:
                    name = winreg.EnumKey(key, index)
                    sub = winreg.OpenKey(key, name)
                except OSError:
                    continue
                try:
                    display, _kind = winreg.QueryValueEx(sub, "DisplayName")
                    if "retroarch" not in str(display).lower():
                        continue
                    location, _kind = winreg.QueryValueEx(sub, "InstallLocation")
                except OSError:
                    continue
                finally:
                    winreg.CloseKey(sub)
                if location:
                    found.append(str(Path(str(location)) / "retroarch.exe"))
        finally:
            winreg.CloseKey(key)
    app_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\retroarch.exe"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\retroarch.exe"),
    ]
    for hive, path in app_paths:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            value, _kind = winreg.QueryValueEx(key, "")
        except OSError:
            value = ""
        finally:
            winreg.CloseKey(key)
        if value:
            found.append(str(value))
    return found


def locate_retroarch(
    configured: str = "",
    *,
    exists=None,
    environ: dict | None = None,
    registry: list[str] | None = None,
    path_value: str | None = None,
) -> str:
    """Config path, then common folders, then the registry, then PATH."""
    exists = os.path.isfile if exists is None else exists
    env = os.environ if environ is None else environ
    configured = str(configured or "").strip()
    if configured and exists(configured):
        return configured
    for candidate in common_exe_candidates(env):
        if exists(candidate):
            return candidate
    sources = registry_retroarch_exes() if registry is None else registry
    for candidate in sources:
        if candidate and exists(candidate):
            return candidate
    raw_path = env.get("PATH", "") if path_value is None else path_value
    text = str(raw_path)
    # A Windows PATH uses ';' and drive-letter colons. Split those on ';'.
    parts = text.split(";") if "\\" in text else text.split(os.pathsep)
    for part in parts:
        if not part:
            continue
        if "\\" in part and "/" not in part:
            candidate = part.rstrip("\\") + "\\retroarch.exe"
        else:
            candidate = str(Path(part) / "retroarch.exe")
        if exists(candidate):
            return candidate
    return ""


def save_retroarch_path(config: Config, exe: str) -> Path | None:
    """Remember the exe on the config object and, when it is a user file, on disk.

    The sample config stays untouched.
    """
    retro = config.data.setdefault("retroarch", {})
    if not isinstance(retro, dict):
        retro = {}
        config.data["retroarch"] = retro
    retro["path"] = exe
    target = config.path
    if target is None:
        return None
    try:
        if Path(target).resolve() == SAMPLE_PATH.resolve():
            log.info("RetroArch path kept in memory. The sample config was not overwritten.")
            return None
    except OSError:
        return None
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config.data, indent=2) + "\n", encoding="utf-8")
    log.info("Saved RetroArch path to %s", target)
    return target


def locate_and_remember(config: Config) -> str:
    configured = str(config.get("retroarch", "path") or "")
    log.info("RetroArch configured path: %r", configured)
    found = locate_retroarch(configured)
    if not found:
        log.info("RetroArch was not found in the config, common folders, the registry, or PATH.")
        return ""
    log.info("RetroArch path: %s", found)
    if os.path.normcase(os.path.normpath(found)) != os.path.normcase(os.path.normpath(configured)):
        save_retroarch_path(config, found)
    return found


def cover_content_in_hole(hole: tuple[int, int, int, int], content_aspect: float) -> tuple[int, int, int, int]:
    """Largest 4:3 (or other) picture that covers the hole. Extra hangs off the edges.

    The frame art is drawn on top, so the cropped edges sit under the painting.
    The picture is never stretched.
    """
    x, y, width, height = (int(v) for v in hole)
    if width < 1 or height < 1 or content_aspect <= 0:
        return x, y, max(1, width), max(1, height)
    if width / height > content_aspect:
        content_w = width
        content_h = max(height, int(round(width / content_aspect)))
    else:
        content_h = height
        content_w = max(width, int(round(height * content_aspect)))
    origin_x = x + (width - content_w) // 2
    origin_y = y + (height - content_h) // 2
    return origin_x, origin_y, content_w, content_h


def tuck_content_in_hole(hole: tuple[int, int, int, int], content_aspect: float,
                         overhang: float = 0.025, limit: float = 0.04) -> tuple[int, int, int, int]:
    """4:3 picture that slips a little under the frame, without eating the HUD.

    About 2.5% of the picture goes under the art on the edges that meet the
    opening. No edge hides more than 4%. When the opening is not 4:3, the
    other axis keeps a gap instead of cropping the health bars and the timer.
    """
    x, y, width, height = (int(v) for v in hole)
    if width < 1 or height < 1 or content_aspect <= 0:
        return x, y, max(1, width), max(1, height)
    _fx, _fy, fit_w, fit_h = fit_content_in_hole((0, 0, width, height), content_aspect)
    overhang = min(max(0.0, overhang), limit)

    def hidden(game: float, hole_size: int) -> float:
        if game <= hole_size or game <= 0:
            return 0.0
        return ((game - hole_size) / 2.0) / game

    # Scale the fitted picture so each tight edge hides `overhang` of the game.
    scale = 1.0 / max(0.5, 1.0 - 2.0 * overhang)
    while scale > 1.0 and max(hidden(fit_w * scale, width), hidden(fit_h * scale, height)) > limit:
        scale *= 0.99
    content_w = max(1, int(round(fit_w * scale)))
    content_h = max(1, int(round(content_w / content_aspect)))
    # Integer rounding can push an edge past the HUD limit. Shrink until it fits.
    while content_w > 1 and content_h > 1 and max(hidden(content_w, width), hidden(content_h, height)) > limit + 0.005:
        content_w -= 1
        content_h = max(1, int(round(content_w / content_aspect)))
    origin_x = x + (width - content_w) // 2
    origin_y = y + (height - content_h) // 2
    return origin_x, origin_y, content_w, content_h


def fit_content_in_hole(hole: tuple[int, int, int, int], content_aspect: float) -> tuple[int, int, int, int]:
    """Largest rectangle of `content_aspect` (width/height) inside the hole.

    A wider hole gets bars on the left and right. A taller hole gets bars on
    the top and bottom. The picture is never stretched.
    """
    x, y, width, height = (int(v) for v in hole)
    if width < 1 or height < 1 or content_aspect <= 0:
        return x, y, max(1, width), max(1, height)
    if width / height > content_aspect:
        content_h = height
        content_w = max(1, int(round(height * content_aspect)))
        content_w = min(content_w, width)
        origin_x = x + (width - content_w) // 2
        origin_y = y
    else:
        content_w = width
        content_h = max(1, int(round(width / content_aspect)))
        content_h = min(content_h, height)
        origin_x = x
        origin_y = y + (height - content_h) // 2
    return origin_x, origin_y, content_w, content_h


def hole_append_config(rect: tuple[int, int, int, int]) -> str:
    """Windowed borderless RetroArch whose client area is the hole.

    The window is the opening. Aspect index 22 is RetroArch's "Core provided",
    so the core's picture is fitted inside that window and the spare space is
    a bar. A custom viewport the size of the window would stretch instead.
    RetroArch's own frame overlay stays off. Buddy already draws the scenery.
    """
    x, y, width, height = (int(v) for v in rect)
    # Slip a 4:3 picture just under the art. A full cover would cut off the HUD
    # when the opening is wider than the game. Integer scale stays off so the
    # picture is not left at 3x in the middle of the window.
    vx, vy, vw, vh = tuck_content_in_hole((0, 0, width, height), SNES_DISPLAY_ASPECT)
    scale = max(vw / 256.0, vh / 224.0, 6.0)
    lines = [
        'video_fullscreen = "false"',
        'video_windowed_fullscreen = "false"',
        'video_window_show_decorations = "false"',
        # True makes RetroArch open AT video_window_width/height. False ignores
        # those and opens at video_scale times the core size (usually 3x).
        'video_window_save_positions = "true"',
        'ui_menubar_enable = "false"',
        # Pause stays on. Clicking the frame pauses the game, and the pause
        # mark stays. Chris likes that.
        f'video_window_x = "{x}"',
        f'video_window_y = "{y}"',
        f'video_window_width = "{width}"',
        f'video_window_height = "{height}"',
        f'video_scale = "{scale:.3f}"',
        'video_scale_integer = "false"',
        'video_crop_overscan = "false"',
        f'aspect_ratio_index = "{ASPECT_RATIO_CUSTOM}"',
        f'custom_viewport_x = "{vx}"',
        f'custom_viewport_y = "{vy}"',
        f'custom_viewport_width = "{vw}"',
        f'custom_viewport_height = "{vh}"',
        'input_overlay_enable = "false"',
    ]
    return "\n".join(lines) + "\n"


def write_hole_config(directory: Path, rect: tuple[int, int, int, int],
                      extras: list[str] | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "buddy-hole.cfg"
    text = hole_append_config(rect).rstrip() + "\n"
    for line in extras or []:
        if line and line not in text:
            text += line.rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def content_args(rom: str, core: str, exists) -> tuple[str, str]:
    """Drop a ROM or core that is not actually there. An empty pair opens the menu."""
    rom = str(rom or "").strip()
    core = str(core or "").strip()
    if rom and not exists(rom):
        log.info("Configured ROM is missing, so RetroArch will open its menu: %s", rom)
        return "", ""
    if core and not exists(core):
        log.info("Configured core is missing, so it was left off the command: %s", core)
        core = ""
    return rom, core


def append_arguments(cfg: Path, rom: str = "", core: str = "") -> list[str]:
    args = ["--appendconfig", str(cfg)]
    if core:
        args.extend(["-L", core])
    if rom:
        args.append(rom)
    return args


def split_launch_extra(extra: list[str]) -> tuple[str, str]:
    """Pull a core and ROM out of the older `-L core rom` argument list."""
    items = [str(item) for item in extra if str(item)]
    if "-L" in items:
        index = items.index("-L")
        core = items[index + 1] if index + 1 < len(items) else ""
        rom = items[index + 2] if index + 2 < len(items) else ""
        return rom, core
    if items:
        return items[-1], ""
    return "", ""


def select_game_hwnd(windows: list[tuple], own_hwnds: set[int]) -> int | None:
    """Prefer a RetroArch window. Class name `RetroArch` counts even if the exe is odd.

    EmulationStation is only used when RetroArch is not open. Buddy's own hwnds never match.
    """
    own = {int(hwnd) for hwnd in own_hwnds if hwnd}
    other = None
    for item in windows:
        if not item:
            continue
        hwnd = int(item[0] or 0)
        if not hwnd or hwnd in own:
            continue
        exe = str(item[1] or "").lower()
        cls = str(item[2] if len(item) > 2 else "")
        if exe == "retroarch.exe" or "retroarch" in exe or cls == "RetroArch":
            return hwnd
        if other is None and "emulationstation" in exe:
            other = hwnd
    return other


def needs_replace(current: tuple[int, int, int, int] | None, target: tuple[int, int, int, int],
                  tolerance: int = 4) -> bool:
    """True when the window is missing or has moved enough to be worth a SetWindowPos."""
    if current is None:
        return True
    return any(abs(int(a) - int(b)) > int(tolerance) for a, b in zip(current, target))


def wait_for_hwnd(poll, timeout: float = 15.0, interval: float = 0.25, sleep=None, clock=None):
    """Poll until a hwnd appears or `timeout` seconds have passed."""
    sleep = time.sleep if sleep is None else sleep
    clock = time.monotonic if clock is None else clock
    deadline = clock() + float(timeout)
    while True:
        found = poll()
        if found:
            return int(found)
        remaining = deadline - clock()
        if remaining <= 0:
            return None
        sleep(min(float(interval), remaining))


def should_close_on_quit(*, launched_by_buddy: bool, close_on_quit: bool) -> bool:
    """Buddy leaves RetroArch running unless it started it and the config says to close it."""
    return bool(launched_by_buddy and close_on_quit)
