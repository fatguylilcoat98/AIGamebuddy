"""Plain words for the hamburger menu.

A person who has never used an emulator should be able to read every line.
The current choice is marked with a check.
"""
from __future__ import annotations

VOICES = (
    ("male", "Man", "A male voice."),
    ("female", "Woman", "A female voice."),
)

ATTITUDES = (
    ("casual", "Chill", "Friendly and calm."),
    ("sassy", "Sassy", "Teases you, and still helps."),
    ("extreme", "Savage-Extreme", "Swears. For adults."),
)

TALK_MODES = (
    ("hold", "Hold a button to talk",
     "Hold the two shoulder buttons for half a second, or hold F9. Select and Start still reach the game, so Buddy does not use those."),
    ("wake", "Say Hey Buddy",
     "Buddy listens for Hey Buddy, then you can talk. If the mic helper is not installed, hold F9."),
)

TALK_AMOUNTS = (
    ("off", "Only when I ask", "Buddy stays quiet until you talk to him."),
    ("normal", "Sometimes", "Buddy speaks once in a while."),
    ("chatty", "A lot", "Buddy talks more often."),
)

SAVE_SLOTS = (1, 2, 3)

# Words that do not belong on a TV menu without a plain explanation beside them.
JARGON = ("cfg", "endpoint", "libretro", "dll", "json", "udp", "shader")


def check_mark(selected: bool) -> str:
    return "✓ " if selected else "    "


def voice_line(key: str, current: str) -> str:
    for ident, label, _note in VOICES:
        if ident == key:
            return f"{check_mark(current == key)}Buddy voice: {label}"
    return ""


def talk_mode_line(key: str, current: str) -> str:
    for ident, label, _note in TALK_MODES:
        if ident == key:
            return f"{check_mark(current == key)}How I talk to Buddy: {label}"
    return ""


def talk_amount_line(key: str, current: str) -> str:
    for ident, label, _note in TALK_AMOUNTS:
        if ident == key:
            return f"{check_mark(current == key)}How much Buddy talks: {label}"
    return ""


def attitude_line(key: str, current: str) -> str:
    for ident, label, _note in ATTITUDES:
        if ident == key:
            return f"{check_mark(current == key)}Buddy attitude: {label}"
    return ""


def menu_lines(voice: str, attitude: str, volume: int, hidden: bool,
               talk_mode: str = "hold", talk_amount: str = "normal") -> list[tuple[str, str]]:
    """(title, one-line explanation) for every row a person sees."""
    rows = [
        ("Start Buddy", "Buddy talks again and shows his face."),
        ("Stop Buddy", "Buddy goes quiet and disappears. Your game keeps playing."),
    ]
    for key, _label, note in TALK_MODES:
        rows.append((talk_mode_line(key, talk_mode), note))
    for key, _label, note in TALK_AMOUNTS:
        rows.append((talk_amount_line(key, talk_amount), note))
    rows.extend([
        ("Save my spot", "Saves exactly where you are."),
        ("Load my spot", "Goes back to your last save."),
    ])
    for key, _label, note in VOICES:
        rows.append((voice_line(key, voice), note))
    for key, _label, note in ATTITUDES:
        rows.append((attitude_line(key, attitude), note))
    rows.extend([
        (f"Volume: {int(volume)}", "Quieter or louder. This is remembered next time."),
        ("Pick a game", "Choose a Super NES game you already own."),
        ("Set up my controller", "Opens the controller page so your buttons match the game."),
        ("RetroArch settings", "Opens RetroArch's menu for the picture, the sound, and the controls."),
        ("Settings", "Optional online helper key, where RetroArch is installed, or run setup again."),
        ("Close the game", "Closes the game. Buddy stays on screen."),
        ("Exit to desktop", "Closes the game and Buddy, and leaves the desktop."),
    ])
    if hidden:
        rows[0] = ("Start Buddy", "Buddy is hidden right now. This brings him back.")
    return rows
