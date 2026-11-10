# Buddy Overlay

Retro games, real attitude. The on-screen name is configurable (`product_name` and `tagline` in `config/buddy.config.sample.json`). The character is Buddy.

This is one Windows app: the approved console frames, Buddy's hologram, memory, voice, and commentary.

Start here on Windows: [WINDOWS_FIRST_RUN.md](WINDOWS_FIRST_RUN.md).
One-download installer: [packaging/build-windows.ps1](packaging/build-windows.ps1) builds `Buddy-Setup.exe`. Licenses: [LICENSES.md](LICENSES.md).
Stream setup: [STREAMING.md](STREAMING.md).
What was actually tested: [VERIFICATION.md](VERIFICATION.md).

## Install

1. Install Python 3.11 or newer and check **Add python.exe to PATH**.
2. Double-click `Start-Buddy.bat`. The first time, and whenever `backend\requirements.txt` changes, it installs into `.venv` and then opens Buddy.
3. Edit `config\buddy.config.json` if you use Ollama. RetroArch is found on its own. Then start Buddy again.
4. `install.bat` is only for a manual repair.

F9 is push-to-talk. F8 focuses the menu under Buddy. Arrow keys and Enter move through it. Ctrl+Shift+Q quits. Buddy speaks. Lines are not drawn over the game window.

`buddy_character` is `male` or `female`. `resting_direction` is `left` (toward the game), `right`, or `center`. The menu toggles those live.

## How auto-lock works

Double-click `Start-Buddy.bat`. Buddy opens the frame and launches RetroArch into the game hole. No separate start, and no manual stretch.

Buddy searches the config path, `C:\RetroArch-Win64`, Program Files, `%APPDATA%\RetroArch`, Steam's `steamapps\common\RetroArch`, Scoop, the registry, and PATH. It saves the exe it finds. If it finds nothing, Buddy's box shows **Find RetroArch**. That control stays off the game.

The launch uses `--appendconfig` with a borderless window the size of the hole, integer scale off, and a custom viewport that fills that window. Buddy then finds the RetroArch hwnd and places it on the hole in real monitor pixels. If the window moves, it is placed again. A RetroArch that is already open is adopted. Quitting Buddy leaves RetroArch running unless `retroarch.close_on_quit` is true.

Each frame in `assets/frames/` has the game window in `assets/frames/metadata.json`. The hole is that rectangle, letterboxed the same way as the overlay. The controller art still overlaps the game by a few pixels, because only near-black pixels are cut out.

`assets/frames/retroarch/*-720p.cfg` and `*-1080p.cfg` are the optional RetroArch-overlay files. Leave them off when Buddy is drawing the frame. ES-DE notes are in `assets/frames/es-de/launch-commands.txt`.

## Add a console

1. Put a 1280x720 JPG in `assets/frames/`. No console logos and no characters from those games.
2. Add the filename to `FRAME_FILES` in `backend/frame_library.py` and the system names to `SYSTEM_ALIASES` (`atari`, `n64`, and so on).
3. Add a `buddy` and `menu` rectangle for that frame in `PLACEMENTS`, in source pixels. The menu bar has to sit under the head. The head rectangle has to cover the baked portrait.
4. Run `python -m backend.frame_library`. That remeasures the black window, writes `metadata.json`, the transparent PNG, and the RetroArch configs.
5. Launch a game for that system. Buddy picks the frame from the alias.

The screen rectangle is the largest near-black area, extended down the side gutters so the footer controller can keep overlapping the game.
