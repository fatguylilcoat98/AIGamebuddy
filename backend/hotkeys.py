"""Hotkeys for the overlay.

Tk bindings only arrive while the overlay window is focused. On Windows a
background poll uses GetAsyncKeyState so F8, F9, and Ctrl+Shift+Q still work
when the game is in front. Tk reports Shift+Q as the keysym Q, so a bind on
lowercase q never quits.
"""
from __future__ import annotations

import os
import threading

QUIT_SEQUENCES = ("<Control-Shift-Q>", "<Control-Shift-q>")

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_Q = 0x51
VK_F8 = 0x77
VK_F9 = 0x78
VK_F11 = 0x7A


def tk_quit_event(event) -> bool:
    key = str(getattr(event, "keysym", "") or "")
    if key.lower() != "q":
        return False
    state = int(getattr(event, "state", 0) or 0)
    # Shift is 0x1. Control is 0x4. Other modifiers set higher bits.
    return bool(state & 0x1) and bool(state & 0x4)


def poll_hotkey_events(previous: dict[str, bool], down: dict[str, bool]) -> list[str]:
    events = []
    if down.get("f9") and not previous.get("f9"):
        events.append("talk_down")
    if previous.get("f9") and not down.get("f9"):
        events.append("talk_up")
    if down.get("f8") and not previous.get("f8"):
        events.append("menu")
    if down.get("f11") and not previous.get("f11"):
        events.append("fullscreen")
    if down.get("quit") and not previous.get("quit"):
        events.append("quit")
    return events


def read_hotkey_state(user32) -> dict[str, bool]:
    def down(vk: int) -> bool:
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    return {
        "f8": down(VK_F8),
        "f9": down(VK_F9),
        "f11": down(VK_F11),
        "quit": down(VK_Q) and down(VK_CONTROL) and down(VK_SHIFT),
    }


def read_shoulder_buttons() -> bool:
    """Both shoulder buttons on a connected pad. False when XInput is missing."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class Gamepad(ctypes.Structure):
            _fields_ = [
                ("wButtons", wintypes.WORD),
                ("bLeftTrigger", wintypes.BYTE),
                ("bRightTrigger", wintypes.BYTE),
                ("sThumbLX", wintypes.SHORT),
                ("sThumbLY", wintypes.SHORT),
                ("sThumbRX", wintypes.SHORT),
                ("sThumbRY", wintypes.SHORT),
            ]

        class State(ctypes.Structure):
            _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", Gamepad)]

        for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                xinput = ctypes.WinDLL(name)
            except OSError:
                continue
            get_state = xinput.XInputGetState
            get_state.argtypes = [wintypes.DWORD, ctypes.POINTER(State)]
            get_state.restype = wintypes.DWORD
            for index in range(4):
                state = State()
                if get_state(index, ctypes.byref(state)) != 0:
                    continue
                buttons = int(state.Gamepad.wButtons)
                if buttons & 0x0100 and buttons & 0x0200:
                    return True
            return False
    except Exception:
        return False
    return False


def start_windows_hotkeys(schedule, stop_event: threading.Event) -> None:
    """Poll global key state on Windows and hand events to `schedule`."""
    if os.name != "nt":
        return

    def loop() -> None:
        import ctypes
        user32 = ctypes.windll.user32
        from .talk_input import shoulder_hold
        previous = {"f8": False, "f9": False, "quit": False}
        shoulders_down = False
        held_for = 0.0
        while not stop_event.is_set():
            down = read_hotkey_state(user32)
            for event in poll_hotkey_events(previous, down):
                schedule(event)
            now_down = read_shoulder_buttons()
            events, held_for = shoulder_hold(shoulders_down, now_down, held_for, 0.03)
            shoulders_down = now_down or held_for > 0
            for event in events:
                schedule(event)
            previous = down
            stop_event.wait(0.03)

    threading.Thread(target=loop, name="buddy-hotkeys", daemon=True).start()
