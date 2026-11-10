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

from . import app_state
from .capture_safety import OVERLAY_SIZE
from .display_info import describe_startup, hole_screen_rect, monitor_rect
from .frame_library import frame_record, paste_head
from .hotkeys import QUIT_SEQUENCES, start_windows_hotkeys, tk_quit_event
from .overlay_view import band_slots, layout_boxes, static_frame
from .retroarch_finder import FIND_LABEL, NOTICE_FAILED, NOTICE_LOOKING, NOTICE_MISSING, save_retroarch_path
from .window_layout import exclude_window_from_capture


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
    import numpy as np
    array = np.array(image.convert("RGBA"))
    transparent = array[:, :, 3] < 16
    array[transparent] = key
    array[~transparent, 3] = 255
    return Image.fromarray(array, "RGBA")


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
    root.resizable(False, False)
    screen = (root.winfo_screenwidth(), root.winfo_screenheight())
    if screen[0] < 640 or screen[1] < 480:
        screen = (1920, 1080)
    if os.name == "nt":
        # Magenta pixels are the game hole. They must not stay a visible pink box.
        root.wm_attributes("-transparentcolor", "magenta")

    holder = {
        "photo": None, "head_photo": None, "fullscreen": True,
        "monitor": screen, "monitor_info": {"left": 0, "top": 0, "width": screen[0], "height": screen[1],
                                            "right": screen[0], "bottom": screen[1], "dpi": None},
        "target": screen, "game": False, "shown": None, "logged_monitor": False,
    }
    background = tk.Label(root, bd=0, bg="black")
    background.place(x=0, y=0, relwidth=1, relheight=1)
    head_label = tk.Label(root, bd=0, bg="black")

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
    windowed = tk.Button(menu, text="Full", command=lambda: _toggle_fullscreen(), **button_style)
    games = tk.Button(menu, text="Games", command=lambda: _toggle_games(), **button_style)
    buttons = [toggle, mode, voice, settings, sound, games, windowed]
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
        windowed.configure(text="Full" if holder["fullscreen"] else "Window")

    def _focus(index: int):
        focus_at["i"] = index % len(buttons)
        buttons[focus_at["i"]].focus_set()

    def _move(delta: int):
        _focus(focus_at["i"] + delta)

    toggle.pack(fill="x", padx=4, pady=(4, 2))
    row = tk.Frame(menu, bg="#12121a")
    row.pack(fill="both", expand=True, padx=2, pady=(0, 4))
    for button in (mode, voice, settings, sound, games, windowed):
        button.pack(in_=row, side="left", expand=True, fill="both", padx=2)
    games_frame = tk.Frame(root, bg="#000000")
    games_list = tk.Listbox(
        games_frame, bg="#000000", fg="#e8f4ff", selectbackground="#1c4a5a",
        highlightthickness=0, bd=0, font=("Segoe UI", 8), activestyle="none",
    )
    games_list.pack(fill="both", expand=True)
    games_entries: list[tuple[str, str]] = []

    def _toggle_games():
        logging.getLogger("buddy.overlay").info("Click: Games")
        holder["games_open"] = not holder.get("games_open")
        _fill_games()
        place_chrome()

    def _fill_games():
        games_list.delete(0, "end")
        games_entries.clear()
        found = session.list_buddy_games()
        labels = {"nes": "NES", "snes": "SNES", "genesis": "Genesis"}
        folder = str(session.config.get("games_dir") or "")
        for system, names in found.items():
            for name in names:
                games_entries.append((str(Path(folder) / {"nes": "NES", "snes": "SNES", "genesis": "Genesis"}[system] / name), system))
                games_list.insert("end", f"{labels.get(system, system)}: {name}")
        if not games_entries:
            games_list.insert("end", "No games in Buddy Games yet")

    def _play_game(_event=None):
        if not games_entries:
            return
        selected = games_list.curselection()
        if not selected:
            return
        rom, system = games_entries[selected[0]]
        logging.getLogger("buddy.overlay").info("Click: play %s", rom)

        def work():
            session.play_listed_game(rom, system)
        threading.Thread(target=work, daemon=True).start()

    games_list.bind("<Double-Button-1>", _play_game)

    def _frame_id():
        return session.theme if session.theme in {"nes", "snes", "genesis"} else "genesis"

    def _read_monitor() -> dict:
        info = monitor_rect(int(root.winfo_id() or 0))
        if not info or info["width"] < 640 or info["height"] < 480:
            width, height = root.winfo_screenwidth(), root.winfo_screenheight()
            if width < 640 or height < 480:
                width, height = screen
            return {
                "left": 0, "top": 0, "right": width, "bottom": height,
                "width": width, "height": height, "dpi": None,
            }
        return info

    def _screen_hole() -> tuple[int, int, int, int]:
        record = frame_record(_frame_id())
        if holder["fullscreen"]:
            info = holder["monitor_info"]
            return hole_screen_rect(record["screen"], (info["left"], info["top"], info["width"], info["height"]))
        return hole_screen_rect(record["screen"], (root.winfo_x(), root.winfo_y(), holder["target"][0], holder["target"][1]))

    def _client_hole() -> tuple[int, int, int, int]:
        record = frame_record(_frame_id())
        return hole_screen_rect(record["screen"], (0, 0, holder["target"][0], holder["target"][1]))

    def _apply_geometry():
        info = _read_monitor()
        holder["monitor_info"] = info
        holder["monitor"] = (info["width"], info["height"])
        if holder["fullscreen"]:
            root.geometry(f"{info['width']}x{info['height']}+{info['left']}+{info['top']}")
            holder["target"] = (info["width"], info["height"])
        else:
            root.geometry(
                f"{OVERLAY_SIZE[0]}x{OVERLAY_SIZE[1]}+{info['left'] + 40}+{info['top'] + 40}"
            )
            holder["target"] = OVERLAY_SIZE
        session._placed = None
        session._borderless.clear()

    def _log_monitor():
        if holder["logged_monitor"]:
            return
        info = holder["monitor_info"]
        width, height = root.winfo_width(), root.winfo_height()
        if width < 640 or height < 480:
            return
        holder["logged_monitor"] = True
        actual = {
            "left": root.winfo_x(), "top": root.winfo_y(),
            "width": width, "height": height,
            "right": root.winfo_x() + width, "bottom": root.winfo_y() + height,
        }
        logging.getLogger("buddy.display").info("%s", describe_startup("fullscreen", actual, info))
        logging.getLogger("buddy.retroarch").info(
            "Hole client=%s screen=%s", _client_hole(), _screen_hole(),
        )

    def _toggle_fullscreen():
        holder["fullscreen"] = not holder["fullscreen"]
        _apply_geometry()
        _rebuild_static()
        _refresh_labels()

    find_btn = tk.Button(root, text=FIND_LABEL, command=lambda: _browse_retroarch(), **button_style)

    def _show_find() -> bool:
        return session.retroarch_notice in {NOTICE_MISSING, NOTICE_FAILED} and not holder["game"]

    def place_chrome():
        boxes = layout_boxes(
            _frame_id(), holder["target"], game_running=holder["game"], reserve_button=_show_find(),
        )
        menu_box = boxes["menu"]
        head_box = boxes["head"]
        menu.place(x=menu_box["x"], y=menu_box["y"], width=menu_box["width"], height=menu_box["height"])
        head_label.place(x=head_box["x"], y=head_box["y"], width=head_box["width"], height=head_box["height"])
        if _show_find():
            button = band_slots(boxes)["button"]
            find_btn.place(x=button["x"], y=button["y"], width=button["width"], height=button["height"])
            find_btn.lift()
        else:
            find_btn.place_forget()
        if holder.get("games_open"):
            from .setup_flow import games_list_rect
            rect = games_list_rect(boxes["buddy"])
            games_frame.place(x=rect["x"], y=rect["y"], width=rect["width"], height=rect["height"])
            games_frame.lift()
        else:
            games_frame.place_forget()
        menu.lift()

    def _rebuild_static():
        image = static_frame(
            _frame_id(), holder["target"], game_running=holder["game"], notice=session.retroarch_notice,
        )
        if os.name == "nt" and holder["game"]:
            image = chroma_key(image)
        holder["photo"] = ImageTk.PhotoImage(image)
        background.configure(image=holder["photo"])
        place_chrome()
        _cut_hole()

    def _browse_retroarch():
        logging.getLogger("buddy.overlay").info("Click: Find RetroArch")
        from tkinter import filedialog
        chosen = filedialog.askopenfilename(
            title=FIND_LABEL,
            filetypes=[("RetroArch", "retroarch.exe"), ("Programs", "*.exe")],
        )
        if not chosen:
            logging.getLogger("buddy.retroarch").info("Find RetroArch was cancelled.")
            return
        save_retroarch_path(session.config, chosen)
        logging.getLogger("buddy.retroarch").info("RetroArch path chosen in Buddy's box: %s", chosen)
        session.retroarch_notice = NOTICE_LOOKING

        def work():
            try:
                session.launch_into_hole(_screen_hole(), force=True)
            except Exception:
                logging.getLogger("buddy.retroarch").exception("Find RetroArch launch failed")
                session.retroarch_notice = NOTICE_FAILED
            root.after(0, _rebuild_static)

        _rebuild_static()
        threading.Thread(target=work, daemon=True).start()

    def _paint_head():
        boxes = layout_boxes(
            _frame_id(), holder["target"], game_running=holder["game"], reserve_button=_show_find(),
        )
        head_box = boxes["head"]
        hud = session.hud()
        expression = hud["expression"]
        mouth = hud["mouth"] if hud["mouth"] else (0.55 if expression == "talk" else 0.0)
        head = render_hologram(
            expression, t=session.clock.mono(), mouth=mouth, gaze=hud["gaze"],
            size=max(head_box["width"], head_box["height"], 64),
            character=hud.get("buddy_character", "male"),
            resting=hud.get("resting_direction", "left"),
            from_expression=hud.get("from_expression"), blend=hud.get("expression_blend", 1.0),
        )
        plate = Image.new("RGBA", (head_box["width"], head_box["height"]), (0, 0, 0, 255))
        plate = paste_head(plate, head, {"x": 0, "y": 0, "width": head_box["width"], "height": head_box["height"]})
        holder["head_photo"] = ImageTk.PhotoImage(plate)
        head_label.configure(image=holder["head_photo"])

    def animate():
        if session.closed:
            return
        session.tick_animation()
        if session.theme != holder.get("shown"):
            holder["shown"] = session.theme
            _rebuild_static()
        _paint_head()
        root.after(80, animate)

    def _cut_hole():
        if os.name != "nt" or not holder["game"] or session.layout != "full":
            return
        root.update_idletasks()
        hole = _client_hole()
        apply_hole_region(root.winfo_id(), holder["target"][0], holder["target"][1], hole)

    def maintain():
        if session.closed:
            return
        current = (root.winfo_width(), root.winfo_height())
        target = holder["target"]
        if current not in {(0, 0), (1, 1)} and (
            current[0] < target[0] - 24 or current[1] < target[1] - 24
        ):
            session.safety.note_geometry(current, time.monotonic(), design=target)
            if session.safety.move_enabled and current != holder.get("snapped"):
                holder["snapped"] = current
                _apply_geometry()
                _rebuild_static()
        hole = _screen_hole()
        session.game_hole = hole
        present = session._emulator_hwnd() is not None
        if present != holder["game"]:
            holder["game"] = present
            session._placed = None
            _rebuild_static()
        if holder["game"] and session.layout == "full" and session.safety.move_enabled:
            session.maintain_layout((root.winfo_x(), root.winfo_y()), target, monitor=target, hole=hole)
        elif not present and session.retroarch_notice in {NOTICE_MISSING, NOTICE_FAILED}:
            place_chrome()
        try:
            session.poll_game_status()
        except Exception:
            logging.getLogger("buddy.retroarch").exception("Game status poll failed")
        root.after(2000, maintain)

    def _boot_retroarch():
        session.retroarch_notice = NOTICE_LOOKING
        _rebuild_static()

        def work():
            try:
                session.launch_into_hole(_screen_hole())
            except Exception:
                logging.getLogger("buddy.retroarch").exception("RetroArch launch failed")
                session.retroarch_notice = NOTICE_FAILED
            root.after(0, _rebuild_static)

        threading.Thread(target=work, name="buddy-retroarch", daemon=True).start()

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
        session.safety.disable("overlay quit", quiet=True)
        try:
            session.close()
        except Exception:
            logging.getLogger("buddy.overlay").exception("Close failed during quit")
        server = app_state.api_server
        if server is not None:
            server.should_exit = True
        try:
            root.destroy()
        except Exception:
            pass

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
    full_once = _once("fullscreen", _toggle_fullscreen)
    # bind_all still works when a menu button has focus. The lowercase q bind
    # does not: Tk's keysym for Shift+Q is Q.
    root.bind_all("<KeyPress-F9>", talk_down_once)
    root.bind_all("<KeyRelease-F9>", talk_up_once)
    root.bind_all("<F8>", menu_once)
    root.bind_all("<F11>", full_once)
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
            "fullscreen": full_once,
            "quit": quit_once,
        }
        action = actions.get(name)
        if action is not None:
            root.after(0, action)

    start_windows_hotkeys(_schedule_hotkey, stop_hotkeys)
    root.protocol("WM_DELETE_WINDOW", _quit)
    app_state.request_quit = lambda: root.after(0, _quit)
    root.update_idletasks()
    session.note_overlay_hwnd(int(root.winfo_id()))
    affinity = exclude_window_from_capture(int(root.winfo_id()))
    logging.getLogger("buddy.overlay").info("Capture affinity for the overlay: %s", affinity)
    _refresh_labels()
    _apply_geometry()
    root.update_idletasks()
    _apply_geometry()
    root.update_idletasks()
    _log_monitor()
    _rebuild_static()
    _focus(0)
    root.after(70, animate)
    root.after(400, _boot_retroarch)
    root.after(1500, maintain)
    root.mainloop()


def ensure_preview_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / "assets" / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path
