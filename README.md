# Buddy Overlay

Retro games, real attitude. The on-screen name is configurable (`product_name` and `tagline` in `config/buddy.config.sample.json`). The character is Buddy.

This is one Windows app: the approved console frames, Buddy's hologram, memory, voice, and commentary.

Start here on Windows: [WINDOWS_FIRST_RUN.md](WINDOWS_FIRST_RUN.md).
Stream setup: [STREAMING.md](STREAMING.md).
What was actually tested: [VERIFICATION.md](VERIFICATION.md).

## Install

1. Install Python 3.11 or newer and check **Add python.exe to PATH**.
2. Double-click `Start-Buddy.bat`. The first time, and whenever `backend\requirements.txt` changes, it installs into `.venv` and then opens Buddy.
3. Edit `config\buddy.config.json` if you use Ollama or want to point at RetroArch, then start Buddy again.
4. `install.bat` is only for a manual repair.

F9 is push-to-talk. F8 focuses the menu under Buddy. Arrow keys and Enter move through it. Ctrl+Shift+Q quits. Buddy speaks. Lines are not drawn over the game window.

`buddy_character` is `male` or `female`. `resting_direction` is `left` (toward the game), `right`, or `center`. The menu toggles those live.

## How auto-lock works

Each frame in `assets/frames/` has a measured game window in `assets/frames/metadata.json`. The same numbers are used two ways:

1. **Buddy's window.** Start Buddy and the 1280x720 frame opens. The black window is transparent. When RetroArch or EmulationStation is the front window, Buddy moves it into that hole. The controller art still overlaps the game, because only near-black pixels were cut out.
2. **RetroArch's own overlay.** `assets/frames/retroarch/*-720p.cfg` and `*-1080p.cfg` set `video_scale_integer` off, aspect ratio Custom, and the viewport for that resolution. Install and Buddy's launcher write a separate cfg for the actual display size, with an absolute overlay path, and turn exclusive fullscreen off. Use windowed fullscreen at that same resolution. A 720p viewport on a different window puts the game outside the hole. ES-DE command lines are in `assets/frames/es-de/launch-commands.txt`.

Use one of those, not both at once. Buddy's window already draws the frame. Adding RetroArch's overlay on top draws it a second time.

`display.mode` in the config (`720p` or `1080p`) chooses which append-config Buddy puts on the RetroArch command when Buddy itself launches a game.

## Add a console

1. Put a 1280x720 JPG in `assets/frames/`. No console logos and no characters from those games.
2. Add the filename to `FRAME_FILES` in `backend/frame_library.py` and the system names to `SYSTEM_ALIASES` (`atari`, `n64`, and so on).
3. Add a `buddy` and `menu` rectangle for that frame in `PLACEMENTS`, in source pixels. The menu bar has to sit under the head. The head rectangle has to cover the baked portrait.
4. Run `python -m backend.frame_library`. That remeasures the black window, writes `metadata.json`, the transparent PNG, and the RetroArch configs.
5. Launch a game for that system. Buddy picks the frame from the alias.

The screen rectangle is the largest near-black area, extended down the side gutters so the footer controller can keep overlapping the game.
