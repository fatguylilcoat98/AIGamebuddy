"""Plain words for the compact hamburger menu.

A person who has never used an emulator should be able to read every line.
Multi-choice settings are dropdowns. On/off settings are checkboxes.
Hover a row to read what it does.
"""
from __future__ import annotations

VOICES = (
    ("male", "Man", "Buddy speaks with a male voice."),
    ("female", "Woman", "Buddy speaks with a female voice."),
)

ATTITUDES = (
    ("casual", "Friendly", "Friendly and calm."),
    ("sassy", "Sassy", "Teases you, and still helps."),
    ("extreme", "Savage-Extreme", "18+. Curses and roasts. Funny, not mean about who you are."),
)

# Hands-free only. Kept in this file so old tests can still import the name,
# but the menu no longer offers a talk-mode or a push-to-talk button.
TALK_MODES = (
    ("hold", "Hold a button to talk",
     "Hold the two shoulder buttons for half a second, or hold F9. Select and Start still reach the game, so Buddy does not use those."),
    ("wake", "Say Hey Buddy",
     "Buddy listens for Hey Buddy, then you can talk. If the mic helper is not installed, hold F9."),
)

TALK_AMOUNTS = (
    ("off", "Only when I ask", "Buddy stays quiet until you talk to him."),
    ("rare", "A little", "Buddy speaks now and then, with a longer pause between lines."),
    ("normal", "Sometimes", "Buddy speaks once in a while."),
    ("chatty", "A lot", "Buddy talks more often, with only a short gap between lines."),
)

SAVE_SLOTS = (1, 2, 3)

GAME_FITS = (
    ("wide", "Wide", "Stretches the game to fill the wide opening in the frame."),
    ("fit", "Fit", "Keeps the whole game picture in view, with a little empty space if needed."),
    ("fill", "Fill", "Zooms the game so the opening is full. The edges may be cropped."),
)

from .look_schedule import LOOK_INTERVALS

LOOK_EVERY = LOOK_INTERVALS

# Words that do not belong on a TV menu without a plain explanation beside them.
JARGON = ("cfg", "endpoint", "libretro", "dll", "json", "udp", "shader")


def check_mark(selected: bool) -> str:
    return "✓ " if selected else "    "


def _label(rows, key: str) -> str:
    for ident, label, _note in rows:
        if ident == key:
            return label
    return str(key)


def voice_line(key: str, current: str) -> str:
    return f"Buddy voice: {_label(VOICES, current if current else key)}"


def talk_mode_line(key: str, current: str) -> str:
    for ident, label, _note in TALK_MODES:
        if ident == key:
            return f"{check_mark(current == key)}How I talk to Buddy: {label}"
    return ""


def talk_amount_line(key: str, current: str) -> str:
    return f"How much Buddy talks: {_label(TALK_AMOUNTS, current if current else key)}"


def look_label(seconds: int) -> str:
    if int(seconds) == 60:
        return "1 minute"
    return f"{int(seconds)} seconds"


def look_line(seconds: int, current: int) -> str:
    return f"How often Buddy looks: {look_label(current if current else seconds)}"


def attitude_line(key: str, current: str) -> str:
    return f"Buddy attitude: {_label(ATTITUDES, current if current else key)}"


def game_fit_line(key: str, current: str) -> str:
    return f"Game picture: {_label(GAME_FITS, current if current else key)}"


def menu_lines(voice: str, attitude: str, volume: int, hidden: bool,
               talk_mode: str = "hold", talk_amount: str = "normal",
               look_interval: int = 10, game_fit: str = "wide",
               muted: bool = False) -> list[tuple[str, str]]:
    """(title, one-line explanation) for every row a person sees."""
    def note_for(table, key, fallback):
        for ident, _label, note in table:
            if ident == key:
                return note
        for ident, _label, note in table:
            if ident == fallback:
                return note
        return ""

    rows = [
        ("Start Buddy", "Buddy talks again and shows his face."),
        ("Stop Buddy", "Buddy goes quiet and disappears. Your game keeps playing."),
        (
            "Just talk",
            "Buddy is always listening. There is no button to push.",
        ),
        (talk_amount_line(talk_amount, talk_amount), note_for(TALK_AMOUNTS, talk_amount, "normal")),
        (look_line(look_interval, look_interval),
         "Buddy looks at the game this often and can talk about what he just saw."),
        (game_fit_line(game_fit, game_fit), note_for(GAME_FITS, game_fit, "wide")),
        (voice_line(voice, voice), note_for(VOICES, voice, "male")),
        (attitude_line(attitude, attitude), note_for(ATTITUDES, attitude, "sassy")),
        (f"Volume: {int(volume)}", "Quieter or louder. This is remembered next time."),
        (("✓ " if muted else "    ") + "Mute",
         "When this is checked, Buddy still shows lines but does not play them out loud."),
        ("Save my spot", "Saves exactly where you are."),
        ("Load my spot", "Goes back to your last save."),
        ("Pick a game", "Choose a Super NES game you already own."),
        ("Set up my controller", "Opens the controller page so your buttons match the game."),
        ("RetroArch settings", "Opens RetroArch's menu for the picture, the sound, and the controls."),
        ("More settings", "Optional online helper key, where RetroArch is installed, or run setup again."),
        ("Close the game", "Closes the game. Buddy stays on screen."),
        ("Exit to desktop", "Closes the game and Buddy, and leaves the desktop."),
    ]
    if hidden:
        rows[0] = ("Start Buddy", "Buddy is hidden right now. This brings him back.")
    return rows
