"""The top-left menu. One compact page of dropdowns and checkboxes.

The button stays clickable while a game is running because the overlay cuts
that rectangle back out of the click-through hole. The menu lives in its own
Toplevel so hover and any light scrolling stay smooth while the overlay
pauses its 30 fps head redraw.
"""
from __future__ import annotations

import os
from pathlib import Path

from .look_schedule import LOOK_INTERVALS
from .menu_copy import (
    ATTITUDES, GAME_FITS, SAVE_SLOTS, TALK_AMOUNTS, VOICES,
    look_label,
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


class HoverTip:
    """Plain-words tooltip that appears after a short hover.

    The bubble is placed on the menu panel (not a second top-level window),
    so it stays with the menu and does not fight the overlay.
    """

    def __init__(self, widget, text: str, host):
        self.widget = widget
        self.text = text
        self.host = host
        self._job = None
        self.tip = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")

    def _enter(self, _event=None):
        self._cancel()
        self._job = self.widget.after(400, self.show)

    def _leave(self, _event=None):
        self._cancel()
        self.hide()

    def _cancel(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def show(self, _event=None):
        self._cancel()
        if self.tip is not None or not (self.text or "").strip():
            return
        import tkinter as tk
        tip = tk.Frame(self.host, bg="#2a2038", highlightbackground="#7ee7ff", highlightthickness=1)
        tk.Label(
            tip, text=self.text, bg="#2a2038", fg="#f6f1ff",
            font=("Segoe UI", 13), justify="left", wraplength=340,
            padx=10, pady=8, relief="flat",
        ).pack()
        tip.update_idletasks()
        host_x, host_y = int(self.host.winfo_rootx()), int(self.host.winfo_rooty())
        wx, wy = int(self.widget.winfo_rootx()), int(self.widget.winfo_rooty())
        x = max(8, wx - host_x + 12)
        y = wy - host_y + int(self.widget.winfo_height()) + 4
        # Keep the bubble inside the panel.
        tip.update_idletasks()
        tw, th = int(tip.winfo_reqwidth()), int(tip.winfo_reqheight())
        hw, hh = max(1, int(self.host.winfo_width())), max(1, int(self.host.winfo_height()))
        if y + th > hh - 6:
            y = max(6, wy - host_y - th - 4)
        if x + tw > hw - 6:
            x = max(6, hw - tw - 6)
        tip.place(x=x, y=y)
        tip.lift()
        self.tip = tip

    def hide(self, _event=None):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


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
        self._scan_anchor = None
        self._exit_anchor = None
        self._tips: list[HoverTip] = []
        self._shown_tip: HoverTip | None = None
        self._layout_job = None
        self.toast = tk.Label(
            root, text="", bg="#140c1c", fg="#f6f1ff", font=("Segoe UI", 16, "bold"),
            padx=14, pady=8,
        )
        self.panel = tk.Toplevel(root)
        self.panel.withdraw()
        self.panel.overrideredirect(True)
        try:
            self.panel.transient(root)
            self.panel.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.panel.configure(bg="#140c1c", highlightthickness=3, highlightbackground="#7ee7ff")
        self.canvas = tk.Canvas(self.panel, bg="#140c1c", highlightthickness=0, bd=0)
        self.scroll = tk.Scrollbar(self.panel, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.inner = tk.Frame(self.canvas, bg="#140c1c")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.inner.bind("<MouseWheel>", self._wheel)
        self.panel.protocol("WM_DELETE_WINDOW", self.close)
        self._rebuild()

    def _wheel(self, event):
        if not self.open or not self._needs_scroll():
            return
        steps = int(-event.delta / 120) if event.delta else 0
        if not steps:
            steps = -1 if getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(steps, "units")

    def _needs_scroll(self) -> bool:
        try:
            return int(self.inner.winfo_reqheight()) > int(self.canvas.winfo_height()) + 8
        except Exception:
            return False

    def toggle(self):
        self.open = not self.open
        if self.open:
            self.page = "main"
            self._rebuild()
        self.place(self._box)
        self.on_change()

    def scroll_to_bottom(self):
        self._fit_scroll()
        if self._needs_scroll():
            self.canvas.yview_moveto(1.0)

    def scroll_to_scan(self):
        """The look-interval row is on the first page now, so no jump is needed."""
        self._fit_scroll()
        self.canvas.yview_moveto(0)

    def scroll_to_saves(self):
        """Bring Save my spot into view if the window is unusually short."""
        self._fit_scroll()
        widget = self._save_anchor
        if widget is None or not self._needs_scroll():
            return
        total = max(1, int(self.inner.winfo_reqheight()))
        y = int(widget.winfo_y())
        self.canvas.yview_moveto(min(0.9, max(0.0, (y - 8) / float(total))))

    def _fit_scroll(self):
        self.root.update_idletasks()
        self.inner.update_idletasks()
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
        if self._needs_scroll():
            if not self.scroll.winfo_ismapped():
                self.scroll.pack(side="right", fill="y")
        else:
            self.scroll.pack_forget()
            self.canvas.yview_moveto(0)

    def _cancel_layout_job(self):
        if self._layout_job is not None:
            try:
                self.panel.after_cancel(self._layout_job)
            except Exception:
                pass
            self._layout_job = None

    def sync_layout(self) -> None:
        """Measure at the final width, then map (or resize) the panel once
        at its real height. Growing the window to the full overlay first
        left stale pixels under the panel, and a delayed fit left the
        first paint with clipped rows. Withdraw only while measuring an
        unmapped panel so an already-open menu does not flicker.
        """
        if not self.open:
            return
        self._cancel_layout_job()
        width = min(560, max(420, int(self._box["width"]) * 4))
        root_x = int(self.root.winfo_rootx())
        root_y = int(self.root.winfo_rooty())
        top = int(self._box["y"]) + int(self._box["height"]) + 12
        screen_h = int(self.root.winfo_height() or 800)
        available = max(240, screen_h - top - 24)
        x = root_x + int(self._box["x"])
        y = root_y + int(top)
        pad = 16 + 2 * int(self.panel.cget("highlightthickness") or 0)
        inner_w = max(100, width - pad)
        try:
            already = bool(self.panel.winfo_viewable())
        except Exception:
            already = False

        if not already:
            # Measure off-screen at the final width so OptionMenu/Scale
            # report their real sizes without a too-short or too-tall map.
            self.panel.withdraw()
            self.panel.geometry(f"{width}x{available}+{x}+{y}")
            self.panel.update_idletasks()
            self.canvas.itemconfigure(self._window, width=inner_w)
            self.inner.update_idletasks()
            self.canvas.update_idletasks()
            content_h = int(self.inner.winfo_reqheight()) + pad
            height = max(240, min(available, content_h))
            self.panel.geometry(f"{width}x{height}+{x}+{y}")
            self.panel.deiconify()
            self.panel.lift()
            for _ in range(30):
                self.panel.update()
                try:
                    if self.panel.winfo_viewable() and int(self.panel.winfo_height()) >= min(height, 240):
                        break
                except Exception:
                    pass
        else:
            self.canvas.itemconfigure(self._window, width=inner_w)
            self.inner.update_idletasks()
            self.canvas.update_idletasks()
            content_h = int(self.inner.winfo_reqheight()) + pad
            height = max(240, min(available, content_h))
            self.panel.geometry(f"{width}x{height}+{x}+{y}")
            self.panel.update_idletasks()

        # One correction if mapping changed the canvas width (scrollbar).
        mapped_w = int(self.canvas.winfo_width() or inner_w)
        if abs(mapped_w - inner_w) > 2:
            self.canvas.itemconfigure(self._window, width=max(100, mapped_w))
            self.inner.update_idletasks()
            content_h = int(self.inner.winfo_reqheight()) + pad
            height = max(240, min(available, content_h))
            self.panel.geometry(f"{width}x{height}+{x}+{y}")
            self.panel.update_idletasks()
        self.panel.update()
        self._fit_scroll()
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self.panel.lift()

    def row_geometry(self) -> dict[str, tuple[int, int, int, int, int, int]]:
        """Map visible label text to (root_x, root_y, w, h, rel_y, rel_x)."""
        found: dict[str, tuple[int, int, int, int, int, int]] = {}

        def walk(widget):
            try:
                text = str(widget.cget("text") or "").strip()
            except Exception:
                text = ""
            if text:
                try:
                    found[text] = (
                        int(widget.winfo_rootx()),
                        int(widget.winfo_rooty()),
                        int(widget.winfo_width()),
                        int(widget.winfo_height()),
                        int(widget.winfo_y()),
                        int(widget.winfo_x()),
                    )
                except Exception:
                    pass
            for child in widget.winfo_children():
                walk(child)

        walk(self.inner)
        return found

    def close(self):
        if not self.open:
            return
        self.open = False
        self._cancel_layout_job()
        self._hide_tips()
        self.panel.withdraw()
        self.on_change()

    def place(self, box: dict[str, int]):
        # The bars are painted into the frame. A widget here would cover them.
        self._box = box
        if not self.open:
            self.panel.withdraw()
            return
        self.sync_layout()

    def panel_rect(self) -> tuple[int, int, int, int] | None:
        if not self.open:
            return None
        try:
            rx, ry = int(self.root.winfo_rootx()), int(self.root.winfo_rooty())
            return (
                int(self.panel.winfo_rootx()) - rx,
                int(self.panel.winfo_rooty()) - ry,
                int(self.panel.winfo_width()),
                int(self.panel.winfo_height()),
            )
        except Exception:
            return None

    def button_rect(self) -> tuple[int, int, int, int]:
        box = self._box
        return (int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"]))

    def contains(self, x: int, y: int) -> bool:
        bx, by, bw, bh = self.button_rect()
        if bx <= x <= bx + bw and by <= y <= by + bh:
            return True
        panel = self.panel_rect()
        if panel is None:
            return False
        px, py, pw, ph = panel
        return px <= x <= px + pw and py <= y <= py + ph

    def _hide_tips(self):
        for tip in self._tips:
            tip.hide()
        self._tips = []
        self._shown_tip = None

    def _clear(self):
        self._hide_tips()
        for child in self.inner.winfo_children():
            child.destroy()

    def _font(self, size: int, bold: bool = False):
        return ("Segoe UI", size, "bold" if bold else "normal")

    def _tip(self, widget, text: str) -> HoverTip:
        tip = HoverTip(widget, text, self.panel)
        self._tips.append(tip)
        return tip

    def _title(self, text: str):
        import tkinter as tk
        tk.Label(self.inner, text=text, bg="#140c1c", fg="#7ee7ff", font=self._font(16, True),
                 anchor="w").pack(fill="x", padx=14, pady=(8, 2))

    def _note(self, text: str):
        import tkinter as tk
        widget = tk.Label(self.inner, text=text, bg="#140c1c", fg="#c8bdd6", font=self._font(12),
                          anchor="w", justify="left", wraplength=500)
        widget.pack(fill="x", padx=16, pady=(0, 4))
        return widget

    def _row(self):
        import tkinter as tk
        row = tk.Frame(self.inner, bg="#140c1c")
        row.pack(fill="x", padx=14, pady=3)
        return row

    def _button(self, text: str, command, primary: bool = False, parent=None, tip: str = ""):
        import tkinter as tk
        holder = parent if parent is not None else self.inner
        button = tk.Button(
            holder, text=text, command=command, anchor="w",
            bg="#7ee7ff" if primary else "#2a2038",
            fg="#140c1c" if primary else "#f6f1ff",
            activebackground="#b8f4ff" if primary else "#3c3050",
            activeforeground="#140c1c" if primary else "#ffffff",
            font=self._font(13, True), relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
        )
        if parent is None:
            button.pack(fill="x", padx=14, pady=3)
        else:
            button.pack(side="left", fill="x", expand=True, padx=3)
        if tip:
            self._tip(button, tip)
        return button

    def _labeled_dropdown(self, label: str, current: str, choices: list[tuple[str, str]], on_pick, tip: str):
        """One compact row: label on the left, OptionMenu on the right."""
        import tkinter as tk
        row = self._row()
        name = tk.Label(row, text=label, bg="#140c1c", fg="#f6f1ff", font=self._font(13, True), anchor="w")
        name.pack(side="left")
        labels = [item[1] for item in choices]
        key_for = {item[1]: item[0] for item in choices}
        label_for = {item[0]: item[1] for item in choices}
        shown = label_for.get(current, current)
        var = tk.StringVar(value=shown)

        def picked(choice, _var=var):
            key = key_for.get(choice, choice)
            on_pick(key)

        menu = tk.OptionMenu(row, var, *labels, command=picked)
        menu.configure(
            bg="#2a2038", fg="#f6f1ff", activebackground="#3c3050", activeforeground="#ffffff",
            font=self._font(13, True), relief="flat", bd=0, highlightthickness=0,
            width=max(12, max(len(item) for item in labels)), anchor="w", cursor="hand2",
        )
        try:
            menu["menu"].configure(
                bg="#2a2038", fg="#f6f1ff", activebackground="#3c3050",
                activeforeground="#ffffff", font=self._font(13), bd=0, tearoff=0,
            )
        except tk.TclError:
            pass
        menu.pack(side="right")
        self._tip(row, tip)
        self._tip(menu, tip)
        self._tip(name, tip)
        return menu, var

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
        if self.open:
            self.sync_layout()

    def _main_page(self):
        import tkinter as tk
        hud = self.session.hud()
        voice = hud.get("buddy_character") or "male"
        attitude = hud.get("personality") or "sassy"
        hidden = bool(hud.get("buddy_hidden"))
        self._title("Buddy")
        actions = self._row()
        start = self._button(
            "Start Buddy", self._start, primary=hidden, parent=actions,
            tip="Buddy talks again and shows his face." if not hidden else "Buddy is hidden right now. This brings him back.",
        )
        self._button(
            "Stop Buddy", self._stop, parent=actions,
            tip="Buddy goes quiet and disappears. Your game keeps playing.",
        )
        self._note("Just talk. Buddy is always listening — no button to push.")
        self._tip(start, "Buddy talks again and shows his face.")

        talk_amount = getattr(self.session, "frequency", "normal")
        if talk_amount not in {key for key, _label, _note in TALK_AMOUNTS}:
            talk_amount = "normal"
        self._talk_menu, _talk_var = self._labeled_dropdown(
            "How much Buddy talks",
            talk_amount,
            [(key, label) for key, label, _note in TALK_AMOUNTS],
            self._talk_amount,
            "How often Buddy speaks on his own. You can always talk to him. "
            + "A lot keeps a short gap between lines, with no long quiet stretch.",
        )

        every = int(getattr(self.session, "look_interval", 10) or 10)
        look_choices = [(str(seconds), look_label(seconds)) for seconds in LOOK_INTERVALS]
        self._scan_anchor, _look_var = self._labeled_dropdown(
            "How often Buddy looks",
            str(every),
            look_choices,
            lambda value: self._look_every(int(value)),
            "Buddy looks at the game this often and can talk about what he just saw.",
        )

        fit = str(getattr(self.session, "game_fit", None) or "wide")
        try:
            from .retroarch_finder import GAME_FIT
            if not getattr(self.session, "game_fit", None):
                fit = GAME_FIT or "wide"
        except Exception:
            pass
        if fit not in {key for key, _label, _note in GAME_FITS}:
            fit = "wide"
        self._fit_menu, _fit_var = self._labeled_dropdown(
            "Game picture",
            fit,
            [(key, label) for key, label, _note in GAME_FITS],
            self._game_fit,
            "How the game fills the opening in the frame. Wide is the usual couch view.",
        )

        self._voice_menu, _voice_var = self._labeled_dropdown(
            "Buddy voice",
            voice,
            [(key, label) for key, label, _note in VOICES],
            self._voice,
            "The voice Buddy uses when he talks.",
        )
        self._attitude_menu, _attitude_var = self._labeled_dropdown(
            "Buddy attitude",
            attitude,
            [(key, label) for key, label, _note in ATTITUDES],
            self._attitude,
            "Friendly and calm, a little sassy, or 18+ savage. This is sent to Buddy's brain.",
        )

        volume = int(hud.get("volume") or 0)
        vol_row = self._row()
        tk.Label(vol_row, text="Volume", bg="#140c1c", fg="#f6f1ff", font=self._font(13, True),
                 anchor="w").pack(side="left")
        self._volume_label = tk.Label(vol_row, text=str(volume), bg="#140c1c", fg="#7ee7ff",
                                      font=self._font(13, True), width=3)
        self._volume_label.pack(side="right")
        self._volume_var = tk.IntVar(value=volume)
        slider = tk.Scale(
            vol_row, from_=0, to=100, orient="horizontal", variable=self._volume_var,
            command=self._volume_live, showvalue=False, bg="#140c1c", fg="#f6f1ff",
            troughcolor="#3c3050", highlightthickness=0, bd=0, sliderrelief="raised",
            sliderlength=18, activebackground="#7ee7ff",
            length=180, cursor="hand2",
        )
        slider.pack(side="right", padx=8)
        slider.bind("<ButtonRelease-1>", lambda _e: self._volume_commit())
        self._tip(vol_row, "Quieter or louder. This is remembered next time.")
        self._tip(slider, "Quieter or louder. This is remembered next time.")

        muted = bool(getattr(self.session, "muted", False))
        self._mute_var = tk.BooleanVar(value=muted)
        mute = tk.Checkbutton(
            self.inner, text="Mute", variable=self._mute_var, command=self._mute,
            bg="#140c1c", fg="#f6f1ff", activebackground="#140c1c", activeforeground="#ffffff",
            selectcolor="#2a2038", font=self._font(13, True), anchor="w", cursor="hand2",
        )
        mute.pack(fill="x", padx=14, pady=2)
        self._tip(mute, "When this is checked, Buddy still shows lines but does not play them out loud.")

        self._title("Your spot")
        spot = self._row()
        self._save_anchor = self._button(
            "Save my spot", lambda: self._show_slots("save"), parent=spot,
            tip="Saves exactly where you are.",
        )
        self._button(
            "Load my spot", lambda: self._show_slots("load"), parent=spot,
            tip="Goes back to your last save.",
        )

        self._title("Your game")
        games = self._row()
        self._button("Pick a game", self._pick_game, parent=games,
                     tip="Choose a Super NES game you already own.")
        self._button("Set up my controller", self._controller, parent=games,
                     tip="Opens the controller page so your buttons match the game.")
        more = self._row()
        self._button("RetroArch settings", self._retroarch, parent=more,
                     tip="Opens RetroArch's menu for the picture, the sound, and the controls.")
        self._button("More settings", self._show_settings, parent=more,
                     tip="Optional online helper key, where RetroArch is installed, or run setup again.")
        end = self._row()
        self._button("Close the game", self._close_game, parent=end,
                     tip="Closes the game. Buddy stays on screen.")
        self._exit_anchor = self._button(
            "Exit to desktop", self._exit, primary=True, parent=end,
            tip="Closes the game and Buddy, and leaves the desktop.",
        )

    def _settings_page(self):
        self._title("More settings")
        self._button("Back", self._show_main, tip="Go back to the main menu.")
        self._button("Online helper key", self._api_key,
                     tip="Optional. Lets Buddy use an online brain. It stays on this PC, not in a text file you can open.")
        self._button("Where RetroArch is installed", self._retroarch_path,
                     tip="Point Buddy at retroarch.exe if it did not find it.")
        self._button("Run setup again", self._rerun_setup,
                     tip="Opens the first-time setup. Your games stay where they are.")

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
        self._button("Back", self._show_main, tip="Go back to the main menu.")
        for slot in SAVE_SLOTS:
            self._button(f"Slot {slot}", lambda number=slot, save=saving: self._slot(number, save),
                         tip=f"{'Save to' if saving else 'Load'} slot {slot}.")

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
        # Hands-free only. Left so an old caller does not crash.
        self.session.set_talk_mode(name)

    def _talk_amount(self, name: str):
        self.session.set_talk_amount(name)
        self._rebuild()

    def _look_every(self, seconds: int):
        self.session.set_look_interval(seconds)
        self._rebuild()

    def _game_fit(self, name: str):
        if hasattr(self.session, "set_game_fit"):
            self.session.set_game_fit(name)
        else:
            from .retroarch_finder import set_game_fit
            set_game_fit(name)
        self._rebuild()
        self.on_change()

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
            self._rebuild()
            return
        self.session.set_personality(name)
        self._rebuild()
        self.on_change()

    def _confirm_adult(self) -> bool:
        import tkinter.messagebox as messagebox
        return bool(messagebox.askyesno(
            "Buddy",
            "Savage-Extreme swears.\n\nAre you 18 or older?",
            parent=self.panel,
        ))

    def _volume_live(self, value):
        try:
            self._volume_label.configure(text=str(int(float(value))))
        except Exception:
            pass

    def _volume_commit(self, _event=None):
        self.session.set_volume(int(self._volume_var.get()))
        self.on_change()

    def _volume(self, delta: int):
        self.session.set_volume(int(self.session.volume) + delta)
        self._rebuild()

    def _mute(self):
        self.session.set_mute(bool(self._mute_var.get()))
        self.on_change()

    def _pick_game(self):
        import tkinter.filedialog as filedialog
        chosen = filedialog.askopenfilename(
            parent=self.panel,
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
                parent=self.panel,
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
        dialog = tk.Toplevel(self.panel)
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
                messagebox.showerror("Buddy", error, parent=self.panel)

        tk.Button(dialog, text="Save on this PC", command=save, font=self._font(16, True),
                  bg="#7ee7ff", fg="#140c1c", relief="flat", padx=12, pady=8).pack(pady=12)

    def _retroarch_path(self):
        import tkinter.filedialog as filedialog
        from .retroarch_finder import save_retroarch_path
        chosen = filedialog.askopenfilename(
            parent=self.panel, title="Where is RetroArch?",
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
