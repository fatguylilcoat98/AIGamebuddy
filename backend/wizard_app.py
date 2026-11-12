"""One setup window. Back and Next. Closing it saves the step.

On an installed copy, Start-Buddy opens this until Play has been pressed.
A source checkout without runtime\\python.exe keeps launching Buddy directly.
"""
from __future__ import annotations

import logging
import os
import subprocess

from .hidden_process import popen as hidden_popen
import sys
from pathlib import Path

from .setup_catalog import FRAME_CHOICES, RETROARCH_VERSION
from .setup_flow import (
    GAMES_COPY,
    SECRET_NAME,
    MemoryVault,
    WindowsVault,
    apply_config,
    can_leave,
    create_games_tree,
    fresh_state,
    license_hook_status,
    load_state,
    move,
    save_state,
    scan_games,
    scan_summary,
    setup_log,
    sign_hook_status,
    check_stored_key,
)

from .config_loader import ROOT


def bundled_runtime() -> Path | None:
    """The installed interpreter. pythonw so Buddy does not open a console."""
    runtime = ROOT / "runtime"
    for name in ("pythonw.exe", "python.exe"):
        candidate = runtime / name
        if candidate.is_file():
            return candidate
    return None


def should_offer_wizard() -> bool:
    """Installed packages have runtime\\python.exe. A git checkout does not."""
    if bundled_runtime() is None:
        return False
    return not load_state().get("completed")


def _vault():
    if os.name == "nt":
        return WindowsVault()
    return MemoryVault()


def run_wizard(state_file: Path | None = None) -> dict:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    state = load_state(state_file)
    state["license_hook"] = license_hook_status()
    state["sign_hook"] = sign_hook_status()
    vault = _vault()

    root = tk.Tk()
    root.title("Buddy Setup")
    root.geometry("1100x700")
    root.configure(bg="#0c0a12")
    root.minsize(900, 640)

    title = tk.Label(root, bg="#0c0a12", fg="#7ee7ff", font=("Segoe UI", 28, "bold"))
    title.pack(anchor="w", padx=28, pady=(18, 0))
    subtitle = tk.Label(root, bg="#0c0a12", fg="#aaa4ba", font=("Segoe UI", 12), wraplength=1000, justify="left")
    subtitle.pack(anchor="w", padx=28, pady=(4, 8))
    body = tk.Frame(root, bg="#0c0a12")
    body.pack(fill="both", expand=True, padx=28, pady=8)
    status = tk.Label(root, bg="#0c0a12", fg="#f0c14a", font=("Segoe UI", 11), wraplength=1000, justify="left")
    status.pack(anchor="w", padx=28)
    nav = tk.Frame(root, bg="#0c0a12")
    nav.pack(fill="x", padx=28, pady=16)
    style = {
        "font": ("Segoe UI", 14, "bold"), "relief": "flat", "bd": 0,
        "padx": 18, "pady": 10, "cursor": "hand2",
    }

    holder = {"persist": state_file}

    def persist():
        save_state(state, holder["persist"])

    def set_status(text: str, bad: bool = False):
        status.configure(text=text, fg="#ff847a" if bad else "#f0c14a")

    def clear_body():
        for child in body.winfo_children():
            child.destroy()

    def big(parent, text, command, primary=True):
        button = tk.Button(
            parent, text=text, command=command,
            bg="#7ee7ff" if primary else "#302840",
            fg="#0c0a12" if primary else "#f4ecdc",
            activebackground="#b8f3ff" if primary else "#4a4060",
            **style,
        )
        return button

    def show():
        clear_body()
        step = state.get("step") or "welcome"
        if step == "welcome":
            title.configure(text="Welcome to Buddy.")
            subtitle.configure(text="One install. Your games. Your overlay. Close this window and it resumes here.")
            tk.Label(
                body, bg="#0c0a12", fg="#f4ecdc", justify="left", font=("Segoe UI", 14), wraplength=1000,
                text="Buddy puts a console frame around RetroArch and talks while you play.\n\n"
                     "This stays on your user account. It does not ask for an administrator password.",
            ).pack(anchor="w", pady=12)
        elif step == "install":
            title.configure(text="Install RetroArch.")
            subtitle.configure(text=f"Pinned build {RETROARCH_VERSION}, portable, under your user folder.")
            row = tk.Frame(body, bg="#0c0a12")
            row.pack(anchor="w", pady=8)
            big(row, "Install a new copy", _install_new).pack(side="left", padx=(0, 12))
            big(row, "Use my RetroArch", _adopt, primary=False).pack(side="left")
            tk.Label(
                body, bg="#0c0a12", fg="#f4ecdc", justify="left", font=("Segoe UI", 12), wraplength=1000,
                text="Buddy installs Snes9x for Super NES.\n"
                     "Snes9x is free for personal use. It is not included so Buddy can be sold.\n"
                     "NES and Genesis are not part of this setup.\n"
                     "The Python runtime comes with the package. Visual C++ is added only if it is missing.",
            ).pack(anchor="w", pady=12)
            if state.get("install_error"):
                set_status(state["install_error"], bad=True)
                big(body, "Retry", _install_new).pack(anchor="w", pady=8)
            elif state.get("progress"):
                set_status(state["progress"])
            elif state.get("retroarch_path"):
                set_status(f"RetroArch: {state['retroarch_path']}")
        elif step == "games":
            title.configure(text="Get your games.")
            subtitle.configure(text="Buddy only sees files you already own.")
            tk.Label(body, bg="#0c0a12", fg="#f4ecdc", justify="left", font=("Segoe UI", 12), wraplength=1000,
                     text=GAMES_COPY).pack(anchor="w")
            row = tk.Frame(body, bg="#0c0a12")
            row.pack(anchor="w", pady=12)
            big(row, "Create Buddy Games", _make_games).pack(side="left", padx=(0, 12))
            big(row, "Open folder", _open_games, primary=False).pack(side="left", padx=(0, 12))
            big(row, "Scan my games", _scan, primary=False).pack(side="left")
            if state.get("scan"):
                tk.Label(body, bg="#0c0a12", fg="#7ee7ff", justify="left", font=("Segoe UI", 12),
                         text=scan_summary(state["scan"])).pack(anchor="w", pady=8)
        elif step == "overlays":
            title.configure(text="Super NES frame.")
            subtitle.configure(text="Buddy uses the SNES frame. The game sits in the opening. Buddy sits in the BUDDY box.")
            for frame_id, label in FRAME_CHOICES:
                row = tk.Frame(body, bg="#0c0a12")
                row.pack(anchor="w", pady=6)
                tk.Label(row, bg="#0c0a12", fg="#f4ecdc", font=("Segoe UI", 14), width=28, anchor="w",
                         text=label).pack(side="left")
                current = (state.get("frames") or {}).get(frame_id, frame_id)
                tk.Label(row, bg="#0c0a12", fg="#7ee7ff", font=("Segoe UI", 12),
                         text=f"assigned to {current}").pack(side="left", padx=8)
                big(row, "Use this", lambda fid=frame_id: _assign(fid), primary=False).pack(side="left")
        elif step == "ai":
            title.configure(text="What kind of AI do you want?")
            subtitle.configure(text="Voice only. Buddy does not print lines on the game.")
            row = tk.Frame(body, bg="#0c0a12")
            row.pack(anchor="w", pady=8)
            for key, label in (("casual", "Casual"), ("sassy", "Sassy"), ("extreme", "Extreme")):
                primary = state.get("personality") == key
                big(row, label, lambda name=key: _personality(name), primary=primary).pack(side="left", padx=(0, 12))
            if state.get("personality") == "extreme" and not state.get("extreme_confirmed"):
                tk.Label(body, bg="#0c0a12", fg="#f0c14a", font=("Segoe UI", 13),
                         text="Extreme uses profanity. Confirm you are 18 or older.").pack(anchor="w", pady=8)
                big(body, "I am 18 or older", _confirm_age).pack(anchor="w")
            tk.Label(body, bg="#0c0a12", fg="#aaa4ba", font=("Segoe UI", 12), wraplength=1000, justify="left",
                     text="API key, optional. It is stored in Windows Credential Manager or DPAPI, never in the config file."
                     ).pack(anchor="w", pady=(16, 4))
            entry = tk.Entry(body, show="*", font=("Segoe UI", 14), bg="#14121c", fg="#f4ecdc", insertbackground="#f4ecdc", width=40)
            entry.pack(anchor="w", pady=4)
            row = tk.Frame(body, bg="#0c0a12")
            row.pack(anchor="w", pady=8)
            big(row, "Save key", lambda: _save_key(entry.get()), primary=False).pack(side="left", padx=(0, 12))
            big(row, "Test", _test_key, primary=False).pack(side="left")
            holder["key_entry"] = entry
        elif step == "buddy":
            title.configure(text="Male or Female Buddy.")
            subtitle.configure(text="Same name. Different face.")
            row = tk.Frame(body, bg="#0c0a12")
            row.pack(anchor="w", pady=8)
            for key, label in (("male", "Male"), ("female", "Female")):
                big(row, label, lambda name=key: _character(name), primary=state.get("character") == key).pack(side="left", padx=(0, 12))
            big(body, "Play voice sample", _sample).pack(anchor="w", pady=16)
        elif step == "done":
            title.configure(text="You're ready.")
            subtitle.configure(text="Play opens Buddy and puts RetroArch in the screen hole.")
            tk.Label(
                body, bg="#0c0a12", fg="#f4ecdc", justify="left", font=("Segoe UI", 14), wraplength=1000,
                text="Pick a game from Buddy's box, or from RetroArch.\n"
                     "Buddy says the game's name out loud. Nothing is written over the picture.\n\n"
                     "If Buddy does not start, the error is in %LOCALAPPDATA%\\Buddy\\logs\\startup.log.\n"
                     "A license key is not built yet. Code signing waits for your certificate.",
            ).pack(anchor="w")
            big(body, "Play", _play).pack(anchor="w", pady=18)
        else:
            title.configure(text="Buddy")

    def _install_new():
        import json
        from .setup_flow import install_default_cores, install_portable
        state["install_mode"] = "portable"
        state["install_error"] = ""
        bundle = ROOT / "bundled" / "RetroArch"
        pin_path = ROOT / "bundled" / "checksums.json"
        checksums = {}
        if pin_path.is_file():
            checksums = json.loads(pin_path.read_text(encoding="utf-8-sig"))
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        dest = Path(base) / "Buddy" / "RetroArch"

        def progress(_fraction, message):
            state["progress"] = message
            set_status(message)

        if bundled_runtime():
            progress(0.1, "Python runtime is included with Buddy.")
        else:
            progress(0.1, "This checkout has no embedded Python. The Windows package includes one.")
        if (bundle / "retroarch.exe").is_file():
            error = install_portable(bundle, dest, checksums, progress)
            if not error:
                installed, skipped, core_error = install_default_cores(
                    bundle / "cores", dest / "cores", checksums, progress,
                )
                state["cores_installed"] = installed
                state["cores_skipped"] = skipped
                error = core_error
            if not error:
                from .game_status import write_core_shader_presets
                shader = write_core_shader_presets(dest)
                state["retroarch_path"] = str(dest / "retroarch.exe")
                state["progress"] = f"RetroArch is in {dest}. Shader: {shader or 'off'}."
                setup_log(state["progress"])
        else:
            error = (
                "RetroArch is not in this package yet, and its checksum is not pinned, "
                "so Buddy did not download one. Run packaging\\build-windows.ps1, or choose Use my RetroArch."
            )
        if error:
            state["install_error"] = error
            state["retroarch_path"] = state.get("retroarch_path") or ""
            setup_log(error)
            set_status(error, bad=True)
        persist()
        show()

    def _adopt():
        chosen = filedialog.askopenfilename(
            title="Find retroarch.exe",
            filetypes=[("RetroArch", "retroarch.exe"), ("Programs", "*.exe")],
        )
        if not chosen:
            return
        from .setup_flow import adopt_retroarch
        error = adopt_retroarch(Path(chosen))
        if error:
            state["install_error"] = error
            set_status(error, bad=True)
        else:
            state["retroarch_path"] = chosen
            state["install_error"] = ""
            state["progress"] = f"Using {chosen}"
            setup_log(f"Adopted RetroArch at {chosen}")
            set_status(state["progress"])
        persist()
        show()

    def _make_games():
        folder = Path.home() / "Buddy Games"
        create_games_tree(folder)
        state["games_dir"] = str(folder)
        setup_log(f"Games folder {folder}")
        set_status(f"Created {folder}")
        persist()
        show()

    def _open_games():
        folder = state.get("games_dir")
        if not folder:
            set_status("Create the Buddy Games folder first.", bad=True)
            return
        _open_folder(Path(folder))

    def _scan():
        folder = state.get("games_dir")
        if not folder:
            set_status("Create the Buddy Games folder first.", bad=True)
            return
        state["scan"] = scan_games(Path(folder))
        summary = scan_summary(state["scan"])
        setup_log("Scan\n" + summary)
        set_status(summary.replace("\n", "  "))
        persist()
        show()

    def _assign(frame_id: str):
        frames = dict(state.get("frames") or {})
        frames[frame_id] = frame_id
        state["frames"] = frames
        persist()
        show()

    def _personality(name: str):
        state["personality"] = name
        if name != "extreme":
            state["extreme_confirmed"] = False
        persist()
        show()

    def _confirm_age():
        state["extreme_confirmed"] = True
        setup_log("Extreme mode confirmed 18+.")
        persist()
        show()

    def _save_key(value: str):
        error = vault.put(SECRET_NAME, value.strip())
        if error:
            state["api_key_stored"] = False
            set_status(error, bad=True)
            return
        state["api_key_stored"] = True
        entry = holder.get("key_entry")
        if entry is not None:
            entry.delete(0, "end")
        setup_log("API key stored. It was not written to the config.")
        set_status("Key stored. It is not in the config file.")
        persist()

    def _test_key():
        set_status(check_stored_key(vault))

    def _character(name: str):
        state["character"] = name
        persist()
        show()

    def _sample():
        if os.name != "nt":
            set_status("Voice sample needs Windows speech. You can still continue.")
            return
        line = "I'm Buddy. Eyes on the game." if state.get("character") != "female" else "I'm Buddy. Your move."
        try:
            from .audio_out import AudioOutput
            result = AudioOutput().speak(line, volume=80, rate=0, device_name="", mute=False)
            if not result.ok:
                set_status(result.message, bad=True)
                return
            set_status("Played a short sample.")
        except Exception as exc:
            set_status(f"Voice sample did not play. You can still continue. {exc}", bad=True)

    def _play():
        error = can_leave(state, "buddy")
        if error:
            set_status(error, bad=True)
            return
        _write_user_config()
        state["step"] = "done"
        state["completed"] = True
        persist()
        setup_log("Setup completed. Launching Buddy.")
        root.destroy()
        _launch_buddy()

    def _write_user_config():
        from .config_loader import LOCAL_PATH, load_config
        config = load_config(LOCAL_PATH if LOCAL_PATH.exists() else None)
        apply_config(config, state)
        target = LOCAL_PATH
        if config.path and config.path.name != "buddy.config.sample.json":
            target = config.path
        target.parent.mkdir(parents=True, exist_ok=True)
        import json
        text = json.dumps(config.data, indent=2) + "\n"
        secret = vault.get(SECRET_NAME)
        if secret and secret in text:
            raise RuntimeError("Refusing to write the API key into the config.")
        target.write_text(text, encoding="utf-8")
        config.path = target

    def go(delta: int):
        if delta > 0 and state.get("step") == "done":
            _play()
            return
        error = move(state, delta)
        if error:
            set_status(error, bad=True)
            return
        set_status("")
        persist()
        show()

    def on_close():
        persist()
        setup_log(f"Wizard closed on step {state.get('step')}.")
        root.destroy()

    big(nav, "Back", lambda: go(-1), primary=False).pack(side="left")
    big(nav, "Next", lambda: go(1)).pack(side="right")
    root.protocol("WM_DELETE_WINDOW", on_close)
    show()
    if os.environ.get("BUDDY_SMOKE_PLAY") == "1" and state.get("step") == "done":
        root.after(25000, _play)
    root.mainloop()
    return state


def _open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    opener = "xdg-open"
    hidden_popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _launch_buddy() -> None:
    runtime = bundled_runtime()
    python = str(runtime) if runtime else sys.executable
    hidden_popen([python, "-m", "backend.launcher"], cwd=str(ROOT))


def main(argv: list[str] | None = None) -> int:
    from .diagnostics import install
    install()
    logging.getLogger("buddy.startup").info("startup: wizard entry")
    args = list(sys.argv[1:] if argv is None else argv)
    if "--shots" in args:
        from .wizard_pages import write_shots
        write_shots(ROOT / "assets" / "wizard" / "pages")
        return 0
    # An installed copy that already finished setup goes straight to Buddy.
    # A source checkout only does that when --if-needed is set and there is no embedded runtime.
    finished = bool(load_state().get("completed"))
    if "--wizard" not in args and (finished or ("--if-needed" in args and not should_offer_wizard())):
        from .launcher import main as launch
        return launch()
    run_wizard()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
