"""What RetroArch says is running, and which shader to use.

GET_STATUS is a localhost UDP reply. Older builds add crc32. A 2026 change
dropped that field, so both shapes are accepted. Speech uses the result.
The overlay does not draw it.
"""
from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("buddy.status")

GUEST_SHADER = "shaders/shaders_slang/crt/crt-guest-advanced-ntsc.slangp"
LIGHT_SHADER = "shaders/shaders_slang/crt/crt-geom.slangp"
CORE_PRESET_NAMES = ("Snes9x", "FCEUmm", "bsnes", "BlastEm")


@dataclass(frozen=True)
class GameStatus:
    state: str
    system: str
    game: str
    crc: str
    core: str


def system_from_token(token: str) -> str:
    text = (token or "").strip().lower().replace("_", " ").replace("-", " ")
    if "snes" in text or "super nintendo" in text or "super famicom" in text or text == "sfc":
        return "snes"
    if "genesis" in text or "mega drive" in text or "megadrive" in text:
        return "genesis"
    if text == "nes" or "famicom" in text or "entertainment system" in text or text.endswith(" nes"):
        return "nes"
    if "nes" in text and "snes" not in text:
        return "nes"
    return ""


def parse_get_status(reply: str) -> GameStatus:
    """Parse `GET_STATUS PLAYING nes,Game,crc32=ab` or the same line without crc32."""
    text = " ".join((reply or "").replace("\x00", " ").split())
    if not text.upper().startswith("GET_STATUS"):
        return GameStatus("UNKNOWN", "", "", "", "")
    rest = text[len("GET_STATUS"):].strip()
    if not rest:
        return GameStatus("UNKNOWN", "", "", "", "")
    state, _, payload = rest.partition(" ")
    state = state.upper()
    if state == "CONTENTLESS" or not payload:
        return GameStatus(state if state else "UNKNOWN", "", "", "", "")
    crc = ""
    core = ""
    parts = [part.strip() for part in payload.split(",")]
    kept: list[str] = []
    for part in parts:
        lower = part.lower()
        if lower.startswith("crc32="):
            crc = part.split("=", 1)[1].strip().lower()
        elif lower.startswith("core="):
            core = part.split("=", 1)[1].strip()
        else:
            kept.append(part)
    system = system_from_token(kept[0] if kept else "")
    game = ",".join(kept[1:]).strip() if len(kept) > 1 else ""
    return GameStatus(state, system, game, crc, core)


def announce_line(game: str, system: str) -> str:
    labels = {"nes": "NES", "snes": "Super NES", "genesis": "Genesis"}
    label = labels.get(system, "")
    if label:
        return f"You're playing {game} on {label}."
    return f"You're playing {game}."


def stuck_line(personality: str, game: str) -> str:
    """A spoken line. Extreme is rude and still gives a real next step."""
    name = game or "this game"
    if personality == "extreme":
        return (
            f"Come on. You're stuck on {name}. Stop mashing the same button. "
            "Watch the last thing that hit you, then use the item you already have."
        )
    if personality == "sassy":
        return f"Paused on {name}. Look at what just hit you, then try the other door."
    return f"Paused on {name}. Check the room you are in and the item you already picked up."


def query_status(host: str, port: int, timeout: float = 0.25) -> str:
    """Send GET_STATUS to localhost. Empty when RetroArch does not answer."""
    if host not in {"127.0.0.1", "localhost"}:
        log.info("Refusing GET_STATUS to %s. Buddy only talks to localhost.", host)
        return ""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(timeout)
            sock.sendto(b"GET_STATUS", (host, int(port)))
            data, _addr = sock.recvfrom(2048)
        finally:
            sock.close()
    except OSError as exc:
        log.info("GET_STATUS got no reply from %s:%s (%s)", host, port, exc)
        return ""
    return data.decode("utf-8", errors="replace")


def shader_relative(retroarch_dir: Path) -> str:
    """Sharp bilinear on an HD TV. CRT scanlines stay off unless someone turns them on."""
    root = Path(retroarch_dir)
    if (root / "shaders/shaders_slang/interpolation/sharp-bilinear.slangp").is_file():
        return "shaders/shaders_slang/interpolation/sharp-bilinear.slangp"
    return ""


def write_core_shader_presets(retroarch_dir: Path) -> str:
    """Per-core presets so RetroArch can auto-load the CRT shader. Returns which one."""
    relative = shader_relative(retroarch_dir)
    if not relative:
        log.info("No CRT shader preset in %s. Buddy left shaders off.", retroarch_dir)
        return ""
    root = Path(retroarch_dir)
    for name in CORE_PRESET_NAMES:
        folder = root / "config" / name
        folder.mkdir(parents=True, exist_ok=True)
        preset = folder / f"{name}.slangp"
        preset.write_text(f'#reference "{relative}"\n', encoding="utf-8")
        (folder / f"{name}.cfg").write_text(
            "\n".join([
                'video_shader_enable = "true"',
                f'video_shader = "{preset.resolve().as_posix()}"',
                "",
            ]),
            encoding="utf-8",
        )
    log.info("Shader preset for FCEUmm, bsnes, and BlastEm: %s", relative)
    return relative


def runtime_cfg_lines(retroarch_exe: str) -> list[str]:
    """Network command interface on localhost, plus a shader when the files exist."""
    lines = [
        'network_cmd_enable = "true"',
        'network_cmd_port = "55355"',
        'video_smooth = "true"',
        'video_shader_enable = "false"',
    ]
    from .retroarch_menu import QUICK_MENU_LINES
    lines.extend(QUICK_MENU_LINES)
    if os.environ.get("BUDDY_SMOKE_CMD"):
        # The Windows runner has no dependable GPU driver. GDI still opens a window.
        # Chris's PC keeps RetroArch's own driver.
        lines.append('video_driver = "gdi"')
        lines.append('video_vsync = "false"')
    if retroarch_exe:
        relative = shader_relative(Path(retroarch_exe).resolve().parent)
        if relative:
            lines = [line for line in lines if not line.startswith("video_shader_enable")]
            lines.append('video_shader_enable = "true"')
            lines.append(f'video_shader = "{relative}"')
        else:
            log.info("Sharp-bilinear is not installed. Video smoothing stays on and CRT stays off.")
    return lines
