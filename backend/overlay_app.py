"""Buddy Overlay window.

The approved frame is the window. The game hole is click-through on Windows.
The live hologram covers the baked head. The menu under the head is real
buttons. Nothing is written over the gameplay opening.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from PIL import Image

from .frame_library import frame_record, paste_head, punch_screen, scaled_box, scaled_screen
from .hotkeys import QUIT_SEQUENCES, start_windows_hotkeys, tk_quit_event


def run_menu_action(mutate, refresh, announce=None) -> None:
    """Apply the menu change, refresh the labels, then do the part that can throw.

    Speech used to raise after the setting was saved, and the button never updated.
    """
    mutate()
    refresh()
    if announce is None:
        return
    try:
        announce()
    except Exception:
        logging.getLogger("buddy.overlay").exception("Menu action failed")
        refresh()


def chroma_key(image, key=(255, 0, 255, 255)):
    """Replace transparent pixels with a color Windows can punch out."""
    rgba = image.convert("RGBA")
    out = []
    for red, green, blue, alpha in rgba.getdata():
        if alpha < 16:
            out.append(key)
        else:
            out.append((red, green, blue, 255))
    keyed = rgba.copy()
    keyed.putdata(out)
    return keyed


def _prepared_frame(frame_id: str) -> Image.Image:
    """Punch the game window only. The portrait bezel stays in the art."""
    record = frame_record(frame_id)
    source = Image.open(Path(__file__).resolve().parents[1] / "assets" / "frames" / record["file"])
    return punch_screen(source, record["screen"])


def run_overlay(session) -> None:
    import tkinter as tk
    from PIL import ImageTk

    from .hologram import render_hologram
    from .window_layout import apply_hole_region

    root = tk.Tk()
    root.title(session.product)
    root.configure(bg="magenta")
    root.attributes("-topmost", True)
    root.overrideredirect(True)
    root.geometry("1280x720+40+40")

    holder = {"photo": None, "base": None}
    background = tk.Label(root, bd=0, bg="magenta")
    background.place(x=0, y=0, relwidth=1, relheight=1)

    button_style = {
        "bg": "#12121a", "fg": "#f4f4f4", "activebackground": "#2c2c3a",
        "activeforeground": "#ffffff", "relief": "flat", "bd": 0,
        "font": ("Segoe UI", 9), "highlightthickness": 1, "highlightbackground": "#3a3a48",
    }
    menu = tk.Frame(root, bg="#12121a")
    toggle = tk.Button(menu, text="Buddy: Male", command=lambda: _toggle_character(), **button_style)
    mode = tk.Button(menu, text="Mode", command=lambda: _cycle_mode(), **button_style)
    voice = tk.Button(menu, text="Voice", command=lambda: _toggle_voice(), **button_style)
    settings = tk.Button(menu, text="Settings", command=lambda: _cycle_rest(), **button_style)
    sound = tk.Button(menu, text="Sound", command=lambda: _step_volume(), **button_style)
    buttons = [toggle, mode, voice, settings, sound]
    focus_at = {"i": 0}

    def _toggle_character():
        current = session.hud().get("buddy_character", "male")
        nxt = "female" if current == "male" else "male"

        def mutate():
            session.buddy_character = nxt
            session._save_ui()

        run_menu_action(mutate, _refresh_labels, lambda: session.set_buddy_character(nxt))

    def _cycle_mode():
        order = ["casual", "sassy", "extreme"]
        current = session.hud().get("personality", "sassy")
        nxt = order[(order.index(current) + 1) % len(order)] if current in order else "sassy"

        def mutate():
            session.personality = nxt

        run_menu_action(mutate, _refresh_labels, lambda: session.set_personality(nxt))

    def _toggle_voice():
        nxt = not session.muted

        def mutate():
            session.muted = nxt

        run_menu_action(mutate, _refresh_labels, lambda: session.set_mute(nxt))

    def _cycle_rest():
        order = ["left", "center", "right"]
        current = session.hud().get("resting_direction", "left")
        nxt = order[(order.index(current) + 1) % len(order)] if current in order else "left"

        def mutate():
            session.resting_direction = nxt

        run_menu_action(mutate, _refresh_labels, lambda: session.set_resting_direction(nxt))

    def _step_volume():
        nxt = 0 if session.volume >= 100 else session.volume + 20

        def mutate():
            session.volume = nxt

        run_menu_action(mutate, _refresh_labels, lambda: session.set_volume(nxt))

    def _refresh_labels():
        hud = session.hud()
        who = "Female" if hud.get("buddy_character") == "female" else "Male"
        toggle.configure(text=f"Buddy: {who}")
        mode.configure(text=f"Mode: {hud.get('personality', '').title()}")
        voice.configure(text="Voice off" if session.muted else "Voice on")
        settings.configure(text=f"Rest: {hud.get('resting_direction', 'left')}")
        sound.configure(text=f"Sound {session.volume}")

    def _focus(index: int):
        focus_at["i"] = index % len(buttons)
        buttons[focus_at["i"]].focus_set()

    def _move(delta: int):
        _focus(focus_at["i"] + delta)

    toggle.pack(fill="x", padx=4, pady=(4, 2))
    row = tk.Frame(menu, bg="#12121a")
    row.pack(fill="both", expand=True, padx=2, pady=(0, 4))
    for button in (mode, voice, settings, sound):
        button.pack(in_=row, side="left", expand=True, fill="both", padx=2)

    def place_chrome():
        width = max(root.winfo_width(), 1)
        height = max(root.winfo_height(), 1)
        frame_id = session.theme if session.theme in {"nes", "snes", "genesis"} else "genesis"
        menu_box = scaled_box(frame_id, "menu", (width, height))
        if menu_box:
            menu.place(x=menu_box[0], y=menu_box[1], width=menu_box[2], height=menu_box[3])
            menu.lift()

    def redraw_frame():
        frame_id = session.theme if session.theme in {"nes", "snes", "genesis"} else "genesis"
        image = _prepared_frame(frame_id)
        image = image.resize((max(root.winfo_width(), 2), max(root.winfo_height(), 2)))
        holder["base"] = image
        _paint()

    def _paint():
        base = holder.get("base")
        if base is None:
            return
        hud = session.hud()
        expression = hud["expression"]
        mouth = hud["mouth"] if hud["mouth"] else (0.55 if expression == "talk" else 0.0)
        frame_id = session.theme if session.theme in {"nes", "snes", "genesis"} else "genesis"
        buddy = scaled_box(frame_id, "buddy", base.size)
        head = render_hologram(
            expression, t=session.clock.mono(), mouth=mouth, gaze=hud["gaze"],
            size=max(buddy[2], buddy[3], 64) if buddy else 64,
            character=hud.get("buddy_character", "male"),
            resting=hud.get("resting_direction", "left"),
            from_expression=hud.get("from_expression"), blend=hud.get("expression_blend", 1.0),
        )
        frame = paste_head(base, head, {"x": buddy[0], "y": buddy[1], "width": buddy[2], "height": buddy[3]}) if buddy else base
        if os.name == "nt":
            frame = chroma_key(frame)
        holder["photo"] = ImageTk.PhotoImage(frame)
        background.configure(image=holder["photo"])

    def animate():
        session.tick_animation()
        _paint()
        if session.theme != holder.get("shown"):
            holder["shown"] = session.theme
            redraw_frame()
            place_chrome()
            _cut_hole()
        root.after(70, animate)

    def _cut_hole():
        if os.name != "nt" or session.layout != "full":
            return
        root.update_idletasks()
        frame_id = session.theme if session.theme in {"nes", "snes", "genesis"} else "genesis"
        hole = scaled_screen(frame_id, (root.winfo_width(), root.winfo_height()))
        if hole:
            apply_hole_region(root.winfo_id(), root.winfo_width(), root.winfo_height(), hole)

    def maintain():
        if session.layout == "full":
            session.maintain_layout((root.winfo_x(), root.winfo_y()), (root.winfo_width(), root.winfo_height()))
        root.after(1500, maintain)

    def talk_down(_event=None):
        session.start_talking()

    def talk_up(_event=None):
        def work():
            session.finish_talking()
        import threading
        threading.Thread(target=work, daemon=True).start()

    recent_hotkey = {}
    stop_hotkeys = threading.Event()

    def _quit(_event=None):
        stop_hotkeys.set()
        root.destroy()

    def _once(name, fn):
        def wrapped(_event=None):
            now = time.monotonic()
            if now - recent_hotkey.get(name, 0.0) < 0.2:
                return
            recent_hotkey[name] = now
            fn()
        return wrapped

    def _maybe_quit(event):
        if tk_quit_event(event):
            _once("quit", _quit)()

    talk_down_once = _once("talk_down", talk_down)
    talk_up_once = _once("talk_up", talk_up)
    menu_once = _once("menu", lambda: _focus(0))
    quit_once = _once("quit", _quit)
    # bind_all still works when a menu button has focus. The lowercase q bind
    # does not: Tk's keysym for Shift+Q is Q.
    root.bind_all("<KeyPress-F9>", talk_down_once)
    root.bind_all("<KeyRelease-F9>", talk_up_once)
    root.bind_all("<F8>", menu_once)
    for sequence in QUIT_SEQUENCES:
        root.bind_all(sequence, quit_once)
    root.bind_all("<KeyPress>", _maybe_quit)
    root.bind("<Tab>", lambda _event: _move(1))
    root.bind("<Right>", lambda _event: _move(1))
    root.bind("<Left>", lambda _event: _move(-1))
    root.bind("<Up>", lambda _event: _focus(0))
    root.bind("<Down>", lambda _event: _focus(1))
    root.bind("<Return>", lambda _event: buttons[focus_at["i"]].invoke())

    def _schedule_hotkey(name: str):
        actions = {
            "talk_down": talk_down_once,
            "talk_up": talk_up_once,
            "menu": menu_once,
            "quit": quit_once,
        }
        action = actions.get(name)
        if action is not None:
            root.after(0, action)

    start_windows_hotkeys(_schedule_hotkey, stop_hotkeys)
    root.protocol("WM_DELETE_WINDOW", _quit)
    _refresh_labels()
    redraw_frame()
    place_chrome()
    _focus(0)
    root.after(70, animate)
    root.after(1500, maintain)
    root.mainloop()


def ensure_preview_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / "assets" / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path
