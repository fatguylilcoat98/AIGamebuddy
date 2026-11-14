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
from .config_loader import ROOT
from .capture_safety import OVERLAY_SIZE
from .display_info import describe_startup, hole_screen_rect, monitor_rect
from .frame_library import frame_record, paste_head
from .hotkeys import QUIT_SEQUENCES, start_windows_hotkeys, tk_quit_event
from .overlay_view import band_slots, layout_boxes, static_frame
from .retroarch_finder import FIND_LABEL, NOTICE_FAILED, NOTICE_LOOKING, NOTICE_MISSING, save_retroarch_path
from .hamburger_ui import HamburgerMenu, design_box
from .window_layout import exclude_window_from_capture

# 30 fps head redraw on the same thread as the menu made scrolling jitter.
# While the menu is open, keep painting the last head at ~5 fps so the well
# stays filled (frozen-looking) instead of going blank.
LIVE_ANIMATE_MS = 33
MENU_OPEN_ANIMATE_MS = 200


def animate_delay_ms(menu_open: bool) -> int:
    return MENU_OPEN_ANIMATE_MS if menu_open else LIVE_ANIMATE_MS


def should_paint_head(menu_open: bool) -> bool:
    # Always paint. The delay is what we slow down, not the head itself.
    return True


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
        "menu_open": False,
    }
    background = tk.Label(root, bd=0, bg="black")
    background.place(x=0, y=0, relwidth=1, relheight=1)
    head_label = tk.Label(root, bd=0, bg="black")

    button_style = {
        "bg": "#12121a", "fg": "#f4f4f4", "activebackground": "#2c2c3a",
        "activeforeground": "#ffffff", "relief": "flat", "bd": 0,
        "font": ("Segoe UI", 18), "highlightthickness": 1, "highlightbackground": "#3a3a48",
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
        attitude = {"casual": "Friendly", "sassy": "Sassy", "extreme": "Extreme"}.get(
            hud.get("personality", ""), str(hud.get("personality", "")).title(),
        )
        mode.configure(text=f"Mode: {attitude}")
        voice.configure(text="Voice off" if session.muted else "Voice on")
        settings.configure(text=f"Rest: {hud.get('resting_direction', 'left')}")
        sound.configure(text=f"Sound {session.volume}")
        windowed.configure(text="Full" if holder["fullscreen"] else "Window")

    def _focus(index: int):
        focus_at["i"] = index % len(buttons)
        buttons[focus_at["i"]].focus_set()

    def _move(delta: int):
        _focus(focus_at["i"] + delta)

    toggle.pack(fill="x", padx=6, pady=(6, 2))
    for labels in ((mode, voice, settings), (sound, games, windowed)):
        row = tk.Frame(menu, bg="#12121a")
        row.pack(fill="both", expand=True, padx=4, pady=2)
        for button in labels:
            button.pack(in_=row, side="left", expand=True, fill="both", padx=3)
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

    def _screen_picture() -> tuple[int, int, int, int]:
        from .retroarch_finder import picture_on_blue
        return picture_on_blue(_screen_hole())

    def _client_picture() -> tuple[int, int, int, int]:
        # Visible game, minus any edge art, so the title and Buddy stay clickable.
        # "wide" starts from the stretched picture so the gutters click through too.
        from .retroarch_finder import GAME_FIT, picture_on_blue, visible_picture
        if GAME_FIT == "wide":
            rect = picture_on_blue(_client_hole())
        else:
            rect = visible_picture(_client_hole())
        static = holder.get("static")
        if static is not None:
            from .overlay_view import art_free_hole
            rect = art_free_hole(static, rect)
        return rect

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
        if os.name == "nt" and holder["fullscreen"]:
            from .window_layout import raise_overlay_front
            root.update_idletasks()
            info = holder["monitor_info"]
            raised = raise_overlay_front(
                int(root.winfo_id() or 0), info["width"], info["height"], (info["left"], info["top"]),
            )
            logging.getLogger("buddy.overlay").info("Overlay front: %s", raised)

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
        # Closed, the frame ends at the hologram and scenery shows below it.
        # F8 or a click on Buddy opens the menu inside that frame.
        menu_ui._target = holder["target"]
        menu_ui.place(design_box(holder))
        if holder.get("menu_open"):
            menu.place_forget()
        else:
            menu.place_forget()
        head_label.place_forget()
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

    def _rebuild_static():
        holder["static"] = static_frame(
            _frame_id(), holder["target"], game_running=holder["game"], notice=session.retroarch_notice,
        )
        place_chrome()
        _cut_hole()
        _keep_menu_clickable()
        _present(_live_frame())

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
                session.launch_into_hole(_screen_picture(), force=True)
            except Exception:
                logging.getLogger("buddy.retroarch").exception("Find RetroArch launch failed")
                session.retroarch_notice = NOTICE_FAILED
            root.after(0, _rebuild_static)

        _rebuild_static()
        threading.Thread(target=work, daemon=True).start()

    def _live_frame():
        """One offscreen frame. The window image is updated in place, not rebuilt."""
        base = holder.get("static")
        if base is None:
            return None
        image = base.copy()
        boxes = layout_boxes(
            _frame_id(), holder["target"], game_running=holder["game"], reserve_button=_show_find(),
        )
        well = boxes["buddy"]
        hud = session.hud()
        expression = hud["expression"]
        mouth = hud["mouth"] if hud["mouth"] else (0.62 if expression == "talk" else 0.0)
        from .hologram import render_hologram, render_hologram_booth
        moment = session.clock.mono()
        yaw = hud.get("yaw")
        if yaw is None:
            yaw = -0.9
        if hud.get("announcer"):
            head = render_hologram_booth(
                max(well["width"], well["height"], 64), moment, mouth, expression,
                hud.get("speaking_as") or "male",
            )
        else:
            head = render_hologram(
                expression, moment, mouth, size=max(well["width"], well["height"], 64),
                character=hud.get("buddy_character", "male"), resting="left", yaw=float(yaw),
            )
        if not hud.get("buddy_hidden"):
            image = paste_head(image, head, well)
        if os.name == "nt" and holder["game"]:
            image = chroma_key(image)
        return image

    def _present(image):
        if image is None:
            return
        photo = holder.get("photo")
        if photo is None or photo.width() != image.width or photo.height() != image.height:
            holder["photo"] = ImageTk.PhotoImage(image)
            background.configure(image=holder["photo"])
        else:
            photo.paste(image)

    def _paint_head():
        _present(_live_frame())

    def animate():
        if session.closed:
            return
        session.tick_animation()
        if session.theme != holder.get("shown"):
            holder["shown"] = session.theme
            _rebuild_static()
        menu_open = bool(holder.get("menu_open"))
        if should_paint_head(menu_open):
            _paint_head()
        root.after(animate_delay_ms(menu_open), animate)

    def _keep_menu_clickable():
        """The game hole is the only click-through part. Buddy and the menu stay solid."""
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = int(root.winfo_id() or 0)
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            pointer = ctypes.sizeof(ctypes.c_void_p) == 8
            get_long = user32.GetWindowLongPtrW if pointer else user32.GetWindowLongW
            set_long = user32.SetWindowLongPtrW if pointer else user32.SetWindowLongW
            get_long.restype = ctypes.c_longlong if pointer else ctypes.c_long
            set_long.restype = ctypes.c_longlong if pointer else ctypes.c_long
            style = int(get_long(hwnd, -20))  # GWL_EXSTYLE
            transparent = 0x20  # WS_EX_TRANSPARENT
            if style & transparent:
                set_long(hwnd, -20, style & ~transparent)
        except Exception:
            logging.getLogger("buddy.overlay").exception("Could not keep the menu clickable")

    def _keep_rects():
        """Hamburger, Buddy, and the open menu stay solid while the game is click-through."""
        boxes = layout_boxes(
            _frame_id(), holder["target"], game_running=holder["game"], reserve_button=_show_find(),
        )
        buddy = boxes["buddy"]
        kept = [
            menu_ui.button_rect(),
            (buddy["x"], buddy["y"], buddy["width"], buddy["height"]),
        ]
        panel = menu_ui.panel_rect()
        if panel is not None:
            kept.append(panel)
        return tuple(kept)

    def _cut_hole():
        if os.name != "nt" or not holder["game"] or session.layout != "full":
            return
        root.update_idletasks()
        hole = _client_picture()
        apply_hole_region(
            root.winfo_id(), holder["target"][0], holder["target"][1], hole, keep=_keep_rects(),
        )

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
        if os.name == "nt" and holder["fullscreen"]:
            from .window_layout import raise_overlay_front
            info = holder["monitor_info"]
            raise_overlay_front(
                int(root.winfo_id() or 0), info["width"], info["height"], (info["left"], info["top"]),
            )
        hole = _screen_picture()
        session.game_hole = hole
        if os.name == "nt" and holder["game"]:
            from .retroarch_finder import GAME_FIT, blue_backing_rect
            if GAME_FIT != "wide":
                from .window_layout import place_blue_backing
                place_blue_backing(blue_backing_rect(_screen_hole()))
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
        try:
            session.maybe_look_at_game()
        except Exception:
            logging.getLogger("buddy.retroarch").exception("Game look failed")
        root.after(2000, maintain)

    def _boot_retroarch():
        session.retroarch_notice = NOTICE_LOOKING
        _rebuild_static()

        def work():
            try:
                session.launch_into_hole(_screen_picture())
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
        session.exit_to_desktop()

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
    def _toggle_menu():
        menu_ui.toggle()
        holder["menu_open"] = menu_ui.open
        if holder["menu_open"]:
            _focus(0)

    def _close_menu():
        if menu_ui.open:
            menu_ui.close()
            holder["menu_open"] = False

    def _click_buddy(event):
        hx, hy, hw, hh = menu_ui.button_rect()
        on_button = hx <= event.x <= hx + hw and hy <= event.y <= hy + hh
        if on_button:
            _toggle_menu()
            return
        if menu_ui.open and not menu_ui.contains(event.x, event.y):
            _close_menu()
            return
        boxes = layout_boxes(
            _frame_id(), holder["target"], game_running=holder["game"], reserve_button=_show_find(),
        )
        buddy = boxes["buddy"]
        inside = (
            buddy["x"] <= event.x <= buddy["x"] + buddy["width"]
            and buddy["y"] <= event.y <= buddy["y"] + buddy["height"]
        )
        if inside and not holder.get("menu_open"):
            _toggle_menu()

    background.bind("<Button-1>", _click_buddy)
    menu_once = _once("menu", _toggle_menu)
    quit_once = _once("quit", _quit)
    full_once = _once("fullscreen", _toggle_fullscreen)
    # bind_all still works when a menu button has focus. The lowercase q bind
    # does not: Tk's keysym for Shift+Q is Q.
    # Hands-free: F9 is no longer push-to-talk. The always-on brain mic listens.
    root.bind_all("<F8>", menu_once)
    root.bind_all("<F11>", full_once)
    for sequence in QUIT_SEQUENCES:
        root.bind_all(sequence, quit_once)
    root.bind_all("<KeyPress>", _maybe_quit)
    root.bind_all("<Escape>", lambda _event: _close_menu())
    root.bind("<Tab>", lambda _event: _move(1))
    root.bind("<Right>", lambda _event: _move(1))
    root.bind("<Left>", lambda _event: _move(-1))
    root.bind("<Up>", lambda _event: _focus(0))
    root.bind("<Down>", lambda _event: _focus(1))
    root.bind("<Return>", lambda _event: buttons[focus_at["i"]].invoke())

    def _schedule_hotkey(name: str):
        actions = {
            # Hands-free: no click-to-talk or shoulder PTT. Just talk.
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
    from .window_layout import toplevel_hwnd
    session.note_overlay_hwnd(toplevel_hwnd(int(root.winfo_id())))
    # Screen-capture exclusion hides the frame from the Windows test grab.
    if os.environ.get("BUDDY_SMOKE_CMD"):
        affinity = "smoke-visible"
    else:
        affinity = exclude_window_from_capture(int(root.winfo_id()))
    logging.getLogger("buddy.overlay").info("Capture affinity for the overlay: %s", affinity)
    _refresh_labels()
    _apply_geometry()
    root.update_idletasks()
    _apply_geometry()
    root.update_idletasks()
    _log_monitor()

    def _menu_changed():
        holder["menu_open"] = menu_ui.open
        place_chrome()
        _cut_hole()
        _paint_head()

    menu_ui = HamburgerMenu(root, session, _menu_changed)
    _rebuild_static()
    _focus(0)

    def _poll_smoke():
        path = os.environ.get("BUDDY_SMOKE_CMD")
        if path:
            command_file = Path(path)
            if command_file.is_file():
                command = command_file.read_text(encoding="utf-8").strip()
                command_file.unlink(missing_ok=True)
                command_file.with_name("smoke-ack.txt").write_text(command, encoding="utf-8")
                if command == "open-menu" and not menu_ui.open:
                    menu_ui.toggle()
                    holder["menu_open"] = True
                elif command == "scroll-menu":
                    menu_ui.open = True
                    menu_ui.page = "main"
                    menu_ui._rebuild()
                    holder["menu_open"] = True
                    menu_ui.place(design_box(holder))
                    root.update_idletasks()
                    menu_ui.scroll_to_bottom()
                    root.after(300, menu_ui.scroll_to_bottom)
                elif command == "scroll-scan":
                    menu_ui.open = True
                    menu_ui.page = "main"
                    menu_ui._rebuild()
                    holder["menu_open"] = True
                    menu_ui.place(design_box(holder))
                    root.update_idletasks()
                    menu_ui.scroll_to_scan()
                elif command == "scroll-saves":
                    menu_ui.open = True
                    menu_ui.page = "main"
                    menu_ui._rebuild()
                    holder["menu_open"] = True
                    menu_ui.place(design_box(holder))
                    menu_ui.scroll_to_saves()
                elif command == "save-load":
                    if menu_ui.open:
                        menu_ui.close()
                        holder["menu_open"] = False
                    saved = session.save_spot(1)
                    loaded = session.load_spot(1)
                    menu_ui._toast(f"{saved.message} {loaded.message}")
                    log_path = os.environ.get("BUDDY_SAVE_LOG")
                    if log_path:
                        Path(log_path).write_text(
                            "\n".join([
                                f"save_ok={saved.ok}",
                                f"save={saved.message}",
                                f"load_ok={loaded.ok}",
                                f"load={loaded.message}",
                                "commands=STATE_SLOT_MINUS x16, STATE_SLOT_PLUS, SAVE_STATE, LOAD_STATE_SLOT 1",
                            ]) + "\n",
                            encoding="utf-8",
                        )
                elif command == "snap":
                    hole = _screen_picture()
                    hwnd = session._emulator_hwnd()
                    if hwnd:
                        session._place_hole(hwnd, hole)
                elif command == "retroarch-menu":
                    session.open_retroarch_menu()
                elif command == "controller":
                    session.open_controller_setup()
                elif command == "pose-talk":
                    session.hold_pose(0.0, "talk", mouth=0.85, seconds=8)
                elif command == "pose-rest":
                    session.hold_pose(-0.92, "idle", mouth=0.0, seconds=8)
                elif command == "exit":
                    session.exit_to_desktop()
        root.after(400, _poll_smoke)

    menu_ui._target = holder["target"]
    menu_ui.place(design_box(holder))
    root.after(70, animate)
    root.after(400, _boot_retroarch)
    root.after(500, _poll_smoke)
    root.after(1500, maintain)
    root.mainloop()


def ensure_preview_dir() -> Path:
    path = ROOT / "assets" / "previews"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path
