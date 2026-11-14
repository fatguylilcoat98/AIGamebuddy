"""Draw the setup wizard pages. The Tk window and these pictures share the copy.

No console logos and no game characters. The thumbnails are Buddy's own frames.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .setup_catalog import FRAME_CHOICES, RETROARCH_VERSION
from .setup_flow import GAMES_COPY, fresh_state, scan_summary

from .config_loader import ROOT
FRAME_DIR = ROOT / "assets" / "frames"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

W, H = 1280, 720
BG = (12, 10, 18)
PANEL = (28, 24, 42)
CYAN = (126, 231, 255)
MAGENTA = (255, 79, 216)
CREAM = (244, 236, 220)
GOLD = (240, 193, 74)
MUTED = (170, 164, 186)
RED = (255, 132, 122)
GREEN = (128, 214, 156)
FRAME_FILES = {
    "genesis": "genesis-16bit.png",
    "nes": "nes-8bit-dungeon.png",
    "snes": "snes-sky-kingdom.png",
}

SHOTS = (
    ("01-welcome", "welcome", {}),
    ("02-install", "install", {}),
    ("03-install-progress", "install", {"progress": f"Checking RetroArch {RETROARCH_VERSION}. Checksum matches."}),
    ("04-install-retry", "install", {
        "install_error": "The RetroArch file did not match its checksum. Nothing was installed.",
    }),
    ("05-games", "games", {"games_dir": r"C:\Users\Chris\Buddy Games"}),
    ("06-games-scan", "games", {
        "games_dir": r"C:\Users\Chris\Buddy Games",
        "scan": {"nes": ["Owned-1.nes", "Owned-2.nes"], "snes": [], "genesis": ["Owned.md"]},
    }),
    ("07-overlays", "overlays", {}),
    ("08-ai", "ai", {"personality": "sassy"}),
    ("09-ai-extreme", "ai", {"personality": "extreme", "extreme_confirmed": False}),
    ("10-api-key", "ai", {"personality": "casual", "api_key_stored": True, "show_key": True}),
    ("11-buddy-male", "buddy", {"character": "male"}),
    ("12-buddy-female", "buddy", {"character": "female"}),
    ("13-done", "done", {}),
)


def _font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_PATH
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            trial = word if not current else current + " " + word
            if draw.textlength(trial, font=font) <= width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def _button(draw, box, label, fill, ink=BG):
    draw.rounded_rectangle(box, 14, fill=fill)
    font = _font(22, True)
    tw = draw.textlength(label, font=font)
    x = box[0] + (box[2] - box[0] - tw) / 2
    y = box[1] + 16
    draw.text((x, y), label, font=font, fill=ink)


def _chrome(draw, step: str, title: str, subtitle: str):
    draw.rectangle((0, 0, W, H), fill=BG)
    draw.rectangle((0, 0, W, 8), fill=CYAN)
    draw.rectangle((0, H - 8, W, H), fill=MAGENTA)
    draw.text((48, 28), "BUDDY", font=_font(28, True), fill=CYAN)
    draw.text((190, 36), "SETUP", font=_font(18, True), fill=GOLD)
    names = ["Welcome", "Install", "Games", "Overlays", "AI", "Buddy", "Play"]
    ids = ["welcome", "install", "games", "overlays", "ai", "buddy", "done"]
    for index, name in enumerate(names):
        x = 520 + index * 100
        here = ids[index] == step
        color = CYAN if here else MUTED
        draw.rounded_rectangle((x, 34, x + 88, 62), 10, fill=(40, 34, 58) if not here else (18, 48, 62))
        draw.text((x + 8, 40), name, font=_font(14, True), fill=color)
    draw.text((48, 96), title, font=_font(40, True), fill=CREAM)
    draw.text((48, 152), subtitle, font=_font(20), fill=MUTED)


def _nav(draw, back: bool = True, nxt: str = "Next"):
    if back:
        _button(draw, (48, 630, 240, 688), "Back", (48, 42, 64), CREAM)
    _button(draw, (980, 630, 1232, 688), nxt, CYAN, BG)


def render_page(step: str, state: dict | None = None) -> Image.Image:
    state = {**fresh_state(), **(state or {})}
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    if step == "welcome":
        _welcome(draw)
    elif step == "install":
        _install(draw, state)
    elif step == "games":
        _games(draw, state)
    elif step == "overlays":
        _overlays(image, draw, state)
    elif step == "ai":
        _ai(draw, state)
    elif step == "buddy":
        _buddy(image, draw, state)
    elif step == "done":
        _done(draw, state)
    else:
        _chrome(draw, "welcome", "Buddy", "")
    return image


def _welcome(draw):
    _chrome(draw, "welcome", "Welcome to Buddy.", "One install. Your games. Your overlay.")
    body = (
        "Buddy puts a console frame around RetroArch and talks while you play.\n\n"
        "This setup stays on your user account. It does not need an administrator password.\n\n"
        "You can close this window. Buddy remembers the step and opens there next time."
    )
    font = _font(24)
    y = 230
    for line in _wrap(draw, body, font, 1100):
        draw.text((64, y), line, font=font, fill=CREAM)
        y += 36 if line else 16
    _button(draw, (64, 500, 420, 570), "Install Buddy", CYAN, BG)
    _nav(draw, back=False, nxt="Next")


def _install(draw, state):
    _chrome(draw, "install", "Install RetroArch.", f"Pinned build {RETROARCH_VERSION}, in Buddy's own folder.")
    _button(draw, (64, 220, 560, 300), "Install a new copy", CYAN, BG)
    _button(draw, (600, 220, 1100, 300), "Use my RetroArch", (48, 42, 64), CREAM)
    notes = (
        "The new copy is portable, under your Local AppData, no admin.\n"
        "Buddy installs Snes9x for Super NES. That core is for personal use.\n"
        "NES and Genesis are not part of this setup.\n"
        "Buddy's Python runtime is included. The Visual C++ runtime is added only if Windows needs it."
    )
    y = 320
    font = _font(20)
    for line in _wrap(draw, notes, font, 1140):
        draw.text((64, y), line, font=font, fill=CREAM)
        y += 30
    draw.text((64, y + 6), "See LICENSES.md before selling Buddy.", font=_font(16), fill=GOLD)
    if state.get("progress") and not state.get("install_error"):
        draw.rounded_rectangle((64, 520, 1100, 575), 12, fill=(18, 48, 62))
        draw.text((80, 536), state["progress"], font=_font(18), fill=GREEN)
    if state.get("install_error"):
        draw.rounded_rectangle((64, 510, 900, 600), 12, fill=(64, 24, 32))
        draw.text((80, 522), state["install_error"], font=_font(16), fill=RED)
        _button(draw, (80, 552, 250, 588), "Retry", GOLD, BG)
    _nav(draw)


def _games(draw, state):
    _chrome(draw, "games", "Get your games.", "Buddy only sees files you already own.")
    font = _font(20)
    y = 210
    for line in _wrap(draw, GAMES_COPY, font, 1140):
        draw.text((64, y), line, font=font, fill=CREAM)
        y += 30 if line else 12
    folder = state.get("games_dir") or "Buddy Games"
    draw.text((64, y + 8), f"Folder: {folder}", font=_font(18, True), fill=CYAN)
    _button(draw, (64, 560, 280, 610), "Create folder", CYAN, BG)
    _button(draw, (296, 560, 500, 610), "Open folder", (48, 42, 64), CREAM)
    _button(draw, (516, 560, 780, 610), "Scan my games", GOLD, BG)
    if state.get("scan"):
        summary = scan_summary(state["scan"])
        draw.text((800, 500), summary, font=_font(16), fill=CREAM)
    _nav(draw)


def _thumb(frame_id: str, size: tuple[int, int]) -> Image.Image:
    path = FRAME_DIR / FRAME_FILES[frame_id]
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (0, 0, 0))
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def _overlays(image, draw, state):
    _chrome(draw, "overlays", "Super NES frame.", "The game sits in the opening. Buddy sits in the BUDDY box.")
    labels = dict(FRAME_CHOICES)
    systems = tuple(labels)
    for index, frame_id in enumerate(systems):
        x = 64 + index * 400
        draw.rounded_rectangle((x, 220, x + 360, 560), 16, fill=PANEL)
        thumb = _thumb(frame_id, (328, 184))
        image.paste(thumb, (x + 16, 236))
        draw.text((x + 16, 436), labels[frame_id], font=_font(20, True), fill=CREAM)
        assigned = state.get("frames", {}).get(frame_id, frame_id)
        draw.text((x + 16, 472), f"Used for {assigned.upper()}", font=_font(16), fill=CYAN)
        _button(draw, (x + 16, 504, x + 200, 548), "Use this", MAGENTA, BG)
    _nav(draw)


def _ai(draw, state):
    _chrome(draw, "ai", "What kind of AI do you want?", "Voice only. Buddy does not print lines on the game.")
    choices = (("casual", "Casual"), ("sassy", "Sassy"), ("extreme", "Extreme"))
    selected = state.get("personality") or "sassy"
    for index, (key, label) in enumerate(choices):
        x = 64 + index * 280
        fill = CYAN if key == selected else (48, 42, 64)
        ink = BG if key == selected else CREAM
        _button(draw, (x, 220, x + 250, 290), label, fill, ink)
    draw.text((64, 320), "Casual is friendly. Sassy teases. Extreme swears.", font=_font(20), fill=CREAM)
    if selected == "extreme" and not state.get("extreme_confirmed"):
        draw.rounded_rectangle((64, 370, 1100, 470), 12, fill=(64, 24, 32))
        draw.text((80, 388), "Extreme uses profanity. Confirm you are 18 or older.", font=_font(22, True), fill=GOLD)
        _button(draw, (80, 420, 360, 458), "I am 18 or older", GOLD, BG)
    draw.text((64, 500), "API key, optional. Stored in Windows Credential Manager, never in the config file.", font=_font(18), fill=MUTED)
    shown = "stored" if state.get("api_key_stored") else "not stored"
    draw.rounded_rectangle((64, 540, 760, 590), 10, fill=(20, 18, 30))
    draw.text((80, 554), f"Key: {shown}", font=_font(20), fill=CYAN if state.get("api_key_stored") else CREAM)
    _button(draw, (780, 540, 980, 590), "Test", (48, 42, 64), CREAM)
    _nav(draw)


def _buddy(image, draw, state):
    who = state.get("character") or "male"
    _chrome(draw, "buddy", "Male or Female Buddy.", "Same name. Different face. A short voice sample if speech works.")
    for index, (key, label) in enumerate((("male", "Male"), ("female", "Female"))):
        x = 64 + index * 420
        fill = CYAN if who == key else PANEL
        draw.rounded_rectangle((x, 220, x + 380, 560), 16, outline=fill, width=4, fill=PANEL)
        portrait = _portrait(key)
        image.paste(portrait, (x + 90, 240))
        draw.text((x + 24, 470), label, font=_font(28, True), fill=CREAM if who != key else CYAN)
        _button(draw, (x + 24, 510, x + 220, 552), "Choose", MAGENTA if who == key else (48, 42, 64), BG if who == key else CREAM)
    _button(draw, (900, 280, 1210, 350), "Play voice sample", GOLD, BG)
    note = "If Windows speech is missing, Buddy says so. You can still continue."
    y = 370
    for line in _wrap(draw, note, _font(16), 300):
        draw.text((900, y), line, font=_font(16), fill=MUTED)
        y += 22
    _nav(draw)


def _portrait(character: str) -> Image.Image:
    try:
        from .hologram import render_hologram
        head = render_hologram("idle", t=0.2, mouth=0.0, size=200, character=character, resting="left")
        plate = Image.new("RGB", (200, 200), (8, 8, 14))
        plate.paste(head.convert("RGBA"), (0, 0), head.convert("RGBA"))
        return plate
    except Exception:
        plate = Image.new("RGB", (200, 200), (8, 8, 14))
        draw = ImageDraw.Draw(plate)
        draw.ellipse((40, 30, 160, 160), outline=CYAN, width=4)
        return plate


def _done(draw, state):
    _chrome(draw, "done", "You're ready.", "Play opens Buddy and puts RetroArch in the screen hole.")
    lines = [
        "Pick a game from Buddy's box, or from RetroArch's own menu.",
        "Buddy asks RetroArch what is running and says the name out loud.",
        "Nothing is written over the game.",
        "If Buddy does not start, read %LOCALAPPDATA%\\Buddy\\logs\\startup.log. Uninstall is in Windows Settings.",
        "A license key is not built yet. Code signing waits for your certificate.",
    ]
    y = 240
    for line in lines:
        draw.text((72, y), line, font=_font(24), fill=CREAM)
        y += 48
    _button(draw, (72, 520, 420, 600), "Play", CYAN, BG)
    _nav(draw, nxt="Play")


def write_shots(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, step, extra in SHOTS:
        state = fresh_state()
        state.update(extra)
        path = directory / f"{name}.png"
        render_page(step, state).save(path, format="PNG")
        written.append(path)
    return written


if __name__ == "__main__":
    out = ROOT / "assets" / "wizard" / "pages"
    for path in write_shots(out):
        print(path)
