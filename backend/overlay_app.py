"""Single retro overlay window. The hamburger menu calls real session actions."""
from __future__ import annotations

import os
from pathlib import Path

from .layout_spec import BUDDY_SCREEN, CAPTION, HOLE, MENU_BUTTON, scale_rect


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


def run_overlay(session) -> None:
    import tkinter as tk
    from PIL import ImageTk

    from .frames import composite_with_head, render_frame
    from .hologram import EXPRESSIONS, render_hologram
    from .window_layout import apply_hole_region

    root = tk.Tk()
    root.title(session.product)
    root.configure(bg="magenta")
    root.attributes("-topmost", True)
    full = session.layout != "compact"
    if full:
        root.geometry("1280x720+40+40")
        root.overrideredirect(True)
    else:
        root.geometry("420x560+40+40")
        root.overrideredirect(True)

    status = tk.StringVar(value=f"{session.character} is starting.")
    caption = tk.StringVar(value="")
    menu_open = tk.BooleanVar(value=False)
    holder = {"frame": None, "photo": None, "head": None, "theme": None}

    background = tk.Label(root, bd=0, bg="magenta")
    background.place(x=0, y=0, relwidth=1, relheight=1)
    head_label = tk.Label(root, bd=0, bg="#000000")
    caption_label = tk.Label(root, textvariable=caption, fg="#f4fbff", bg="#101820",
                             wraplength=700, justify="left", font=("Segoe UI", 12))
    status_label = tk.Label(root, textvariable=status, fg="#9ad7ff", bg="#101820",
                            wraplength=360, justify="left", font=("Segoe UI", 9))

    menu = tk.Frame(root, bg="#141820", padx=8, pady=8)

    def say_result(result) -> None:
        status.set(result.message or result.reason or "Done.")
        if result.text:
            caption.set(result.text)

    def command(fn):
        def wrapped():
            try:
                say_result(fn())
            except Exception as exc:
                status.set(f"That action failed. {exc}")
        return wrapped

    def add_button(text, fn):
        tk.Button(menu, text=text, command=command(fn), anchor="w").pack(fill="x", pady=1)

    add_button("Casual", lambda: session.set_personality("casual"))
    add_button("Sassy", lambda: session.set_personality("sassy"))
    add_button("Extreme", lambda: session.set_personality("extreme"))
    add_button("Buddy character: Male", lambda: session.set_buddy_character("male"))
    add_button("Buddy character: Female", lambda: session.set_buddy_character("female"))
    add_button("Rest facing the game", lambda: session.set_resting_direction("left"))
    add_button("Rest facing right", lambda: session.set_resting_direction("right"))
    add_button("Rest facing camera", lambda: session.set_resting_direction("center"))
    add_button("Stop insulting me", lambda: session.handle_text("stop insulting me"))
    add_button("Mute", lambda: session.set_mute(True))
    add_button("Unmute", lambda: session.set_mute(False))
    add_button("Volume up", lambda: session.set_volume(session.volume + 10))
    add_button("Volume down", lambda: session.set_volume(session.volume - 10))
    add_button("Commentary rare", lambda: session.set_frequency("rare"))
    add_button("Commentary normal", lambda: session.set_frequency("normal"))
    add_button("Commentary off", lambda: session.set_frequency("off"))
    add_button("8-bit frame", lambda: session.set_theme("nes"))
    add_button("Fantasy frame", lambda: session.set_theme("snes"))
    add_button("Speed frame", lambda: session.set_theme("genesis"))
    add_button("Auto frame", lambda: session.set_theme_auto())
    add_button("Full overlay", lambda: session.set_layout("full"))
    add_button("Compact stream layout", lambda: session.set_layout("compact"))
    add_button("Vision on", lambda: session.set_vision(True))
    add_button("Vision off", lambda: session.set_vision(False))
    add_button("Look at the game", lambda: session.observe_once())
    add_button("What am I playing?", lambda: session.handle_text("what am I playing"))
    add_button("View memory", lambda: session.handle_text("what do you remember"))
    add_button("Reset preferences", lambda: session.reset_memory())
    add_button("Clear all memory", lambda: session.clear_memory())
    add_button("Confirm offline game", lambda: session.set_offline_confirmed(True))
    add_button("Clear offline confirm", lambda: session.set_offline_confirmed(False))
    add_button("Takeover (gated)", lambda: session.request_takeover())
    add_button("Co-op port 2 (gated)", lambda: session.request_coop())
    add_button("Give me the controls", lambda: session.release_control())
    add_button("Cycle expression demo", lambda: cycle_expression)
    entry = tk.Entry(menu)
    entry.pack(fill="x", pady=4)

    def submit(_event=None):
        text = entry.get().strip()
        if text:
            say_result(session.handle_text(text))
            entry.delete(0, "end")

    entry.bind("<Return>", submit)
    tk.Button(menu, text="Say it", command=submit).pack(fill="x")
    add_button("Push-to-talk now", lambda: session.start_talking())
    add_button("Finish talking", lambda: session.finish_talking())
    add_button("Quit", lambda: root.destroy())

    demo_index = {"n": 0}

    def cycle_expression():
        name = EXPRESSIONS[demo_index["n"] % len(EXPRESSIONS)]
        demo_index["n"] += 1
        return session.demo_expression(name)

    def toggle_menu(_event=None):
        if menu_open.get():
            menu.place_forget()
            menu_open.set(False)
        else:
            menu.place(relx=0.76, rely=0.10, relwidth=0.22, relheight=0.62)
            menu_open.set(True)

    def on_click(event):
        width = max(root.winfo_width(), 1)
        height = max(root.winfo_height(), 1)
        rect = scale_rect(MENU_BUTTON, width, height)
        x, y, w, h = rect
        if x <= event.x <= x + w and y <= event.y <= y + h:
            toggle_menu()

    background.bind("<Button-1>", on_click)

    def place_chrome():
        width = max(root.winfo_width(), 1)
        height = max(root.winfo_height(), 1)
        if session.layout == "compact":
            head_label.place(x=70, y=70, width=280, height=280)
            caption_label.place(x=16, y=370, width=388, height=80)
            status_label.place(x=16, y=460, width=388, height=80)
            return
        sx, sy, sw, sh = scale_rect(BUDDY_SCREEN, width, height)
        head_label.place(x=sx, y=sy, width=sw, height=sh)
        cx, cy, cw, ch = scale_rect(CAPTION, width, height)
        caption_label.place(x=cx, y=cy, width=cw, height=ch)
        status_label.place(x=sx, y=max(0, sy - 36), width=sw, height=32)

    def redraw_frame(force=False):
        theme = session.theme if session.layout == "full" else "compact"
        if not force and holder["theme"] == theme and holder["photo"] is not None:
            return
        holder["theme"] = theme
        if session.layout == "compact":
            card = render_frame("genesis", session.banner).image.resize((420, 560))
        else:
            card = render_frame(session.theme, session.banner).image.resize(
                (max(root.winfo_width(), 2), max(root.winfo_height(), 2))
            )
        if os.name == "nt" and session.layout == "full":
            card = chroma_key(card)
        holder["frame"] = card
        holder["photo"] = ImageTk.PhotoImage(card)
        background.configure(image=holder["photo"])

    def animate():
        session.tick_animation()
        hud = session.hud()
        expression = hud["expression"]
        mouth = hud["mouth"] if hud["mouth"] else (0.45 if expression == "talk" else 0)
        head = render_hologram(
            expression, t=session.clock.mono(), mouth=mouth, gaze=hud["gaze"], size=280,
            character=hud.get("buddy_character", "male"),
            resting=hud.get("resting_direction", "left"),
            from_expression=hud.get("from_expression"),
            blend=hud.get("expression_blend", 1.0),
        )
        holder["head"] = ImageTk.PhotoImage(head)
        head_label.configure(image=holder["head"])
        if hud["last_text"] and hud["last_text"] != caption.get():
            caption.set(hud["last_text"])
        if session.layout != ("compact" if holder["theme"] == "compact" else "full") or (
            session.layout == "full" and holder["theme"] not in {session.theme, "compact"}
        ):
            apply_layout()
        root.after(70, animate)

    def apply_layout():
        if session.layout == "compact":
            root.overrideredirect(True)
            corners = {
                "bottom-right": "+1200+400",
                "bottom-left": "+40+400",
                "top-right": "+1200+40",
                "top-left": "+40+40",
            }
            root.geometry("420x560" + corners.get(session.corner, "+40+40"))
        else:
            root.geometry("1280x720+40+40")
        redraw_frame(force=True)
        place_chrome()
        if os.name == "nt" and session.layout == "full":
            root.update_idletasks()
            hole = scale_rect(HOLE, root.winfo_width(), root.winfo_height())
            apply_hole_region(root.winfo_id(), root.winfo_width(), root.winfo_height(), hole)

    def maintain():
        if session.layout == "full":
            result = session.maintain_layout(
                (root.winfo_x(), root.winfo_y()),
                (root.winfo_width(), root.winfo_height()),
            )
            if result.reason not in {"not_windows", "layout_idle"} and result.message:
                status.set(result.message)
        root.after(2000, maintain)

    def talk_down(_event=None):
        say_result(session.start_talking())

    def talk_up(_event=None):
        def work():
            result = session.finish_talking()
            root.after(0, lambda: say_result(result))
        import threading
        threading.Thread(target=work, daemon=True).start()

    root.bind("<KeyPress-F9>", talk_down)
    root.bind("<KeyRelease-F9>", talk_up)
    root.bind("<Control-Shift-q>", lambda _event: root.destroy())
    root.bind("<Escape>", lambda _event: menu.place_forget())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    apply_layout()
    root.after(70, animate)
    root.after(2000, maintain)
    status.set("Hamburger is the top-right button. F9 talks. Ctrl+Shift+Q quits.")
    root.mainloop()


def ensure_preview_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / "assets" / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path
