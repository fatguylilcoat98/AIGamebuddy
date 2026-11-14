"""Open RetroArch's own menu from Buddy.

MENU_TOGGLE is RetroArch's network command for the Quick Menu (or the main
menu when nothing is running). The controller shortcut then moves to Controls.

Buddy's launch config turns on a short Quick Menu so that path stays put:
Resume, Restart, Close Content, Save States, Options, Controls.
"""
from __future__ import annotations

import time

# Downs from the top of that short Quick Menu to the Controls entry.
CONTROLLER_DOWNS = 5

QUICK_MENU_LINES = (
    'quick_menu_show_resume_content = "true"',
    'quick_menu_show_restart_content = "true"',
    'quick_menu_show_close_content = "true"',
    'quick_menu_show_savestate_submenu = "true"',
    'quick_menu_show_options = "true"',
    'quick_menu_show_controls = "true"',
    'quick_menu_show_take_screenshot = "false"',
    'quick_menu_show_start_recording = "false"',
    'quick_menu_show_start_streaming = "false"',
    'quick_menu_show_replay = "false"',
    'quick_menu_show_shaders = "false"',
    'quick_menu_show_cheats = "false"',
)


def retroarch_settings_commands() -> list[str]:
    return ["MENU_TOGGLE"]


def controller_setup_commands(*, menu_already_open: bool) -> list[str]:
    commands: list[str] = []
    if not menu_already_open:
        commands.append("MENU_TOGGLE")
    commands.extend(["MENU_UP"] * 24)
    commands.extend(["MENU_DOWN"] * CONTROLLER_DOWNS)
    commands.append("MENU_OK")
    return commands


def send_commands(client, commands: list[str], pause: float = 0.08, sleep=None) -> str:
    """Send each command. Returns an error sentence, or empty on success."""
    sleeper = time.sleep if sleep is None else sleep
    last = ""
    for command in commands:
        result = client.send(command, requires_control=False, gate_open=False)
        if not result.ok:
            return result.message
        last = result.message
        if pause:
            sleeper(pause)
    return "" if commands else "There was no command to send."
