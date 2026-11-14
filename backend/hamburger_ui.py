"""The top-left menu. Big type, plain words, a check on the current choice.

The button stays clickable while a game is running because the overlay cuts
that rectangle back out of the click-through hole.
"""
from __future__ import annotations

import os
from pathlib import Path

from .look_schedule import LOOK_INTERVALS
from .menu_copy import (
    ATTITUDES, SAVE_SLOTS, TALK_AMOUNTS, VOICES,
    attitude_line, look_line, talk_amount_line, voice_line,
)


def design_box(holder) -> dict[str, int]:
    """Hamburger rectangle in the overlay's current pixels."""
    from .capture_safety import fit_frame
    from .chris_snes_frame import HAMBURGER
    from .frame_library import DESIGN
    origin_x, origin_y, frame_w, frame_h = fit_frame(tuple(holder.get("target") or (DESIGN["width"], DESIGN["height"])))
    sx = frame_w / DESIGN["width"]
    sy = frame_h / DESIGN["height"]
    return {
        "x": int(origin_x + round(HAMBURGER["x"] * sx)),
        "y": int(origin_y + round(HAMBURGER["y"] * sy)),
        "width": max(72, int(round(HAMBURGER["width"] * sx))),
        "height": max(48, int(round(HAMBURGER["height"] * sy))),
    }


class HamburgerMenu:
    def __init__(self, root, session, on_change):
        import tkinter as tk
        self.root = root
        self.session = session
        self.on_change = on_change
        self.open = False
        self.page = "main"
        self._box = {"x": 24, "y": 16, "width": 120, "height": 72}
        self._save_anchor = None
        self.toast = tk.Label(
            root, text="", bg="#140c1c", fg="#f6f1ff", font=("Segoe UI", 16, "bold"),
            padx=14, pady=8,
        )
        self.panel = tk.Frame(root, bg="#140c1c", highlightthickness=3, highlightbackground="#7ee7ff")
        self.canvas = tk.Canvas(self.panel, bg="#140c1c", highlightthickness=0, bd=0)
        self.scroll = tk.Scrollbar(self.panel, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.inner = tk.Frame(self.canvas, bg="#140c1c")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self._rebuild()

    def _wheel(self, event):
        if self.open:
            self.canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")

    def toggle(self):
        self.open = not self.open
        if self.open:
            self.page = "main"
            self._rebuild()
        self.place(self._box)
        self.on_change()

    def scroll_to_bottom(self):
        self.root.update_idletasks()
        self.inner.update_idletasks()
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        widget = getattr(self, "_exit_anchor", None)
        total = max(1, int(self.inner.winfo_reqheight()))
        view = max(1, int(self.canvas.winfo_height()))
        if widget is not None:
            top = max(0, int(widget.winfo_y()) + int(widget.winfo_reqheight()) - view + 4)
            self.canvas.yview_moveto(min(1.0, top / float(total)))
        else:
            self.canvas.yview_moveto(1.0)

    def scroll_to_scan(self):
        """Bring the look-at-the-game choices into view. The menu is already open."""
        self.root.update_idletasks()
        self.inner.update_idletasks()
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        widget = getattr(self, "_scan_anchor", None)
        total = max(1, int(self.inner.winfo_reqheight()))
        y = int(widget.winfo_y()) if widget is not None else int(total * 0.28)
        self.canvas.yview_moveto(min(0.9, max(0.0, (y - 48) / float(total))))

    def scroll_to_saves(self):
        """Bring Save my spot and Load my spot into view. The menu is already open."""
        self.inner.update_idletasks()
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        widget = self._save_anchor
        total = max(1, int(self.inner.winfo_reqheight()))
        y = int(widget.winfo_y()) if widget is not None else int(total * 0.42)
        self.canvas.yview_moveto(min(0.9, max(0.0, (y - 8) / float(total))))

    def close(self):
        if not self.open:
            return
        self.open = False
        self.panel.place_forget()
        self.on_change()

    def place(self, box: dict[str, int]):
        # The bars are painted into the frame. A widget here would cover them.
        self._box = box
        if not self.open:
            self.panel.place_forget()
            return
        width = min(760, max(420, box["width"] * 4))
        top = box["y"] + box["height"] + 12
        screen_h = int(self.root.winfo_height() or 800)
        height = max(240, min(screen_h - top - 24, 920))
        self.panel.place(x=box["x"], y=top, width=width, height=height)
        self.panel.lift()

    def panel_rect(self) -> tuple[int, int, int, int] | None:
        if not self.open:
            return None
        return (
            int(self.panel.winfo_x()), int(self.panel.winfo_y()),
            int(self.panel.winfo_width()), int(self.panel.winfo_height()),
        )

    def button_rect(self) -> tuple[int, int, int, int]:
        box = self._box
        return (box["x"], box["y"], box["width"], box["height"])

    def contains(self, x: int, y: int) -> bool:
        bx, by, bw, bh = self.button_rect()
        if bx <= x <= bx + bw and by <= y <= by + bh:
            return True
        panel = self.panel_rect()
        if panel is None:
            return False
        px, py, pw, ph = panel
        return px <= x <= px + pw and py <= y <= py + ph

    def _clear(self):
        for child in self.inner.winfo_children():
            child.destroy()

    def _font(self, size: int, bold: bool = False):
        return ("Segoe UI", size, "bold" if bold else "normal")

    def _title(self, text: str):
        import tkinter as tk
        tk.Label(self.inner, text=text, bg="#140c1c", fg="#7ee7ff", font=self._font(22, True),
                 anchor="w").pack(fill="x", padx=18, pady=(14, 4))

    def _note(self, text: str):
        import tkinter as tk
        tk.Label(self.inner, text=text, bg="#140c1c", fg="#c8bdd6", font=self._font(15),
                 anchor="w", justify="left", wraplength=680).pack(fill="x", padx=22, pady=(0, 6))

    def _button(self, text: str, command, primary: bool = False):
        import tkinter as tk
        button = tk.Button(
            self.inner, text=text, command=command, anchor="w",
            bg="#7ee7ff" if primary else "#2a2038",
            fg="#140c1c" if primary else "#f6f1ff",
            activebackground="#b8f4ff" if primary else "#3c3050",
            activeforeground="#140c1c" if primary else "#ffffff",
            font=self._font(20, True), relief="flat", bd=0, padx=16, pady=10, cursor="hand2",
        )
        button.pack(fill="x", padx=16, pady=4)
        return button

    def _rebuild(self):
        self._clear()
        if self.page == "settings":
            self._settings_page()
        elif self.page == "save":
            self._slot_page(saving=True)
        elif self.page == "load":
            self._slot_page(saving=False)
        else:
            self._main_page()
        self.canvas.yview_moveto(0)

    def _main_page(self):
        hud = self.session.hud()
        voice = hud.get("buddy_character") or "male"
        attitude = hud.get("personality") or "sassy"
        hidden = bool(hud.get("buddy_hidden"))
        self._title("Buddy")
        self._button("Start Buddy", self._start, primary=hidden)
        self._note("Buddy talks again and shows his face.")
        self._button("Stop Buddy", self._stop)
        self._note("Buddy goes quiet and disappears. Your game keeps playing.")
        talk_amount = getattr(self.session, "frequency", "normal")
        if talk_amount not in {key for key, _label, _note in TALK_AMOUNTS}:
            talk_amount = "normal"
        self._title("How much Buddy talks")
        self._note("Just talk. Buddy is always listening — no button to push.")
        for key, _label, note in TALK_AMOUNTS:
            self._button(talk_amount_line(key, talk_amount), lambda name=key: self._talk_amount(name))
            self._note(note)
        booth = bool(getattr(self.session, "announcer", False))
        self._button(("✓ " if booth else "    ") + "Announcer booth", self._announcer)
        self._note("Guy and girl Buddy call the game. They take turns, and both sit in the box.")
        self._title("How often Buddy looks at the game")
        every = int(getattr(self.session, "look_interval", 10) or 10)
        self._scan_anchor = None
        for seconds in LOOK_INTERVALS:
            button = self._button(look_line(seconds, every), lambda value=seconds: self._look_every(value))
            if self._scan_anchor is None:
                self._scan_anchor = button
        self._note("Buddy looks at the game picture, not the frame around it.")
        self._title("Your spot")
        self._save_anchor = self._button("Save my spot", lambda: self._show_slots("save"))
        self._note("Saves exactly where you are.")
        self._button("Load my spot", lambda: self._show_slots("load"))
        self._note("Goes back to your last save.")
        self._title("Buddy voice")
        for key, _label, note in VOICES:
            self._button(voice_line(key, voice), lambda name=key: self._voice(name))
            self._note(note)
        self._title("Buddy attitude")
        for key, _label, note in ATTITUDES:
            self._button(attitude_line(key, attitude), lambda name=key: self._attitude(name))
            self._note(note)
        self._title(f"Volume: {int(hud.get('volume') or 0)}")
        self._note("Quieter or louder. This is remembered next time.")
        self._button("Quieter", lambda: self._volume(-10))
        self._button("Louder", lambda: self._volume(10))
        self._title("Your game")
        self._button("Pick a game", self._pick_game)
        self._note("Choose a Super NES game you already own.")
        self._button("Set up my controller", self._controller)
        self._note("Opens the controller page so your buttons match the game.")
        self._button("RetroArch settings", self._retroarch)
        self._note("Opens RetroArch's menu for the picture, the sound, and the controls.")
        self._button("Settings", self._show_settings)
        self._note("Optional online helper key, where RetroArch is installed, or run setup again.")
        self._button("Close the game", self._close_game)
        self._note("Closes the game. Buddy stays on screen.")
        self._exit_anchor = self._button("Exit to desktop", self._exit, primary=True)
        self._note("Closes the game and Buddy, and leaves the desktop.")

    def _settings_page(self):
        self._title("Settings")
        self._button("Back", self._show_main)
        self._button("Online helper key", self._api_key)
        self._note("Optional. Lets Buddy use an online brain. It stays on this PC, not in a text file you can open.")
        self._button("Where RetroArch is installed", self._retroarch_path)
        self._note("Point Buddy at retroarch.exe if it did not find it.")
        self._button("Run setup again", self._rerun_setup)
        self._note("Opens the first-time setup. Your games stay where they are.")

    def _show_settings(self):
        self.page = "settings"
        self._rebuild()

    def _show_main(self):
        self.page = "main"
        self._rebuild()

    def _show_slots(self, which: str):
        self.page = which
        self._rebuild()

    def _slot_page(self, *, saving: bool):
        self._title("Save my spot" if saving else "Load my spot")
        self._note("Saves exactly where you are." if saving else "Goes back to your last save.")
        self._button("Back", self._show_main)
        for slot in SAVE_SLOTS:
            label = f"Slot {slot}"
            self._button(label, lambda number=slot, save=saving: self._slot(number, save))

    def _slot(self, number: int, saving: bool):
        if saving:
            result = self.session.save_spot(number)
        else:
            result = self.session.load_spot(number)
        self._toast(result.message)
        self.on_change()

    def _toast(self, text: str):
        self.toast.configure(text=text)
        box = self._box
        self.toast.place(x=box["x"], y=box["y"] + box["height"] + 8)
        self.toast.lift()
        self.root.after(2600, self.toast.place_forget)

    def _talk_mode(self, name: str):
        self.session.set_talk_mode(name)
        self._rebuild()

    def _talk_amount(self, name: str):
        self.session.set_talk_amount(name)
        self._rebuild()

    def _announcer(self):
        self.session.set_announcer(not bool(getattr(self.session, "announcer", False)))
        self._rebuild()

    def _look_every(self, seconds: int):
        self.session.set_look_interval(seconds)
        self._rebuild()

    def _start(self):
        self.session.start_buddy()
        self._rebuild()
        self.on_change()

    def _stop(self):
        self.session.stop_buddy()
        self._rebuild()
        self.on_change()

    def _voice(self, name: str):
        self.session.set_buddy_character(name)
        self._rebuild()
        self.on_change()

    def _attitude(self, name: str):
        if name == "extreme" and not self._confirm_adult():
            return
        self.session.set_personality(name)
        self._rebuild()
        self.on_change()

    def _confirm_adult(self) -> bool:
        import tkinter.messagebox as messagebox
        return bool(messagebox.askyesno(
            "Buddy",
            "Savage-Extreme swears.\n\nAre you 18 or older?",
            parent=self.root,
        ))

    def _volume(self, delta: int):
        self.session.set_volume(int(self.session.volume) + delta)
        self._rebuild()

    def _pick_game(self):
        import tkinter.filedialog as filedialog
        chosen = filedialog.askopenfilename(
            parent=self.root,
            title="Pick a Super NES game you already own",
            filetypes=[("Super NES games", "*.sfc *.smc *.fig *.zip"), ("All files", "*.*")],
        )
        if not chosen:
            return
        continue_spot = False
        if self.session.has_continue(chosen):
            import tkinter.messagebox as messagebox
            continue_spot = bool(messagebox.askyesno(
                "Buddy",
                "Continue where you left off?",
                parent=self.root,
            ))
        self.close()

        def work(resume: bool = continue_spot):
            launch_owned_rom(self.session, chosen, continue_spot=resume)
        import threading
        threading.Thread(target=work, daemon=True).start()

    def _controller(self):
        self.session.open_controller_setup()

    def _retroarch(self):
        self.session.open_retroarch_menu()

    def _close_game(self):
        self.session.close_game()
        self.on_change()

    def _exit(self):
        self.session.exit_to_desktop()

    def _api_key(self):
        import tkinter as tk
        from .setup_flow import SECRET_NAME, WindowsVault, MemoryVault
        dialog = tk.Toplevel(self.root)
        dialog.title("Online helper key")
        dialog.configure(bg="#140c1c")
        dialog.geometry("640x280")
        tk.Label(
            dialog, bg="#140c1c", fg="#f6f1ff", wraplength=580, justify="left", font=self._font(16),
            text="Optional. Paste a key if you want Buddy to use an online brain.\n"
                 "It is saved on this PC and is not written into a text file.",
        ).pack(anchor="w", padx=16, pady=16)
        entry = tk.Entry(dialog, show="*", font=self._font(18), bg="#1c1428", fg="#f6f1ff", width=42)
        entry.pack(padx=16, pady=8)

        def save():
            vault = WindowsVault() if os.name == "nt" else MemoryVault()
            error = vault.put(SECRET_NAME, entry.get().strip())
            dialog.destroy()
            if error:
                import tkinter.messagebox as messagebox
                messagebox.showerror("Buddy", error, parent=self.root)

        tk.Button(dialog, text="Save on this PC", command=save, font=self._font(16, True),
                  bg="#7ee7ff", fg="#140c1c", relief="flat", padx=12, pady=8).pack(pady=12)

    def _retroarch_path(self):
        import tkinter.filedialog as filedialog
        from .retroarch_finder import save_retroarch_path
        chosen = filedialog.askopenfilename(
            parent=self.root, title="Where is RetroArch?",
            filetypes=[("RetroArch", "retroarch.exe"), ("Programs", "*.exe")],
        )
        if chosen:
            save_retroarch_path(self.session.config, chosen)

    def _rerun_setup(self):
        import sys
        from .config_loader import ROOT
        from .hidden_process import popen as hidden_popen
        from .wizard_app import bundled_runtime
        runtime = bundled_runtime()
        python = str(runtime) if runtime else sys.executable
        hidden_popen([python, "-m", "backend.wizard_app", "--wizard"], cwd=str(ROOT))
        self.close()


def launch_owned_rom(session, path: str, continue_spot: bool = False):
    """Play one Super NES file the person already has."""
    from .setup_catalog import default_core_filename
    rom = str(path)
    exe = session._find_retroarch_path()
    core = ""
    if exe:
        candidate = Path(exe).resolve().parent / "cores" / default_core_filename("snes")
        if candidate.is_file():
            core = str(candidate)
    session.theme = "snes"
    session.theme_mode = "snes"
    session.current_rom = rom
    session.continue_on_launch = bool(continue_spot)
    hole = session.game_hole or session._fallback_hole("snes")
    return session.launch_into_hole(hole, force=True, rom=rom, core=core, adopt=False)
