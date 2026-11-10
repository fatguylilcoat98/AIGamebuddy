# First run on Windows

You need Windows 10 or 11 and Python 3.11 or newer.
Buddy was built on a Linux machine. The steps below are what you run on your PC.
Voice, the microphone, the transparent overlay, and emulator windows still need you to try them there.

## 1. Install Python

1. Open https://www.python.org/downloads/windows/
2. Download Python 3.11 or newer.
3. Run the installer.
4. Check **Add python.exe to PATH**.
5. Finish the install.

## 2. Start Buddy

1. Copy this project folder onto the PC (or clone the repo).
2. Double-click `Start-Buddy.bat`.

The first time, and again whenever `backend\requirements.txt` changes, that installs the Python packages into `.venv` and then opens Buddy. You do not run a separate installer first. It also copies `config/buddy.config.sample.json` to `config/buddy.config.json` the first time.

`install.bat` is still there if an install breaks and you want to repair it by hand.

If the window says Python is missing, finish step 1 and make sure PATH was checked, then double-click `Start-Buddy.bat` again.

## 3. Choose how Buddy thinks

Open `config/buddy.config.json` in Notepad.

Leave `"provider": "offline"` if you only want to see the overlay and the menu.
Offline Buddy will not invent walkthroughs. He can still run menu commands.

To use Ollama on this PC (your RTX 3060 can run it):

1. Install Ollama from https://ollama.com and start it.
2. In a terminal run `ollama pull llama3.2` (or another model you already have).
3. In the config set:

```json
"provider": "ollama",
"ollama": { "base_url": "http://127.0.0.1:11434", "model": "llama3.2" }
```

To use Meta's API instead, set `"provider": "meta"`, fill in `meta.model` and `meta.base_url` if Meta gave you a different host, and set a user environment variable. Do not paste the key into the json file.

```text
setx BUDDY_META_API_KEY "your-key-here"
```

Close and reopen the terminal or sign out once so Windows picks up `setx`.
The sample base URL is `https://api.meta.ai/v1`. If that host is wrong for your key, change `meta.base_url` only. Buddy will not pretend the call worked if the key or the URL is rejected.

Vision is separate and off by default. When you have a vision model:

```json
"vision": {
  "provider": "meta",
  "model": "the-vision-model-name",
  "base_url": "https://api.meta.ai/v1",
  "api_key_env": "BUDDY_VISION_API_KEY",
  "enabled": true
}
```

```text
setx BUDDY_VISION_API_KEY "your-vision-key"
```

## 4. Point Buddy at RetroArch (optional)

In the same config file set the real path, for example:

```json
"retroarch": { "path": "C:\\RetroArch\\retroarch.exe", "command_enabled": false }
```

ROM folders look like this. Use your real folders.

```json
"libraries": [
  { "system": "snes", "path": "C:\\ROMs\\SNES", "core": "C:\\RetroArch\\cores\\snes9x_libretro.dll" }
]
```

If the path is empty or wrong, Buddy says he did not launch the program.

Exclusive fullscreen is off. Buddy writes a RetroArch append-config for the current display size, with absolute paths to the overlay, when you run install.bat and again when Buddy launches a game. The game viewport is scaled to that resolution. The cfg name includes the size, such as `nes-1400x900.cfg`.

Use windowed fullscreen at that same resolution. A 720p viewport on a different window (for example 1400x900) puts the game outside the hole. If you start RetroArch yourself, regenerate the configs for the size you actually use:

```text
python -m backend.frame_library --install
```

For Buddy's own overlay hole, a 1280x720 window matches the frame. Do not turn on RetroArch's overlay at the same time, or the frame is drawn twice.

## 5. Start Buddy

Double-click `Start-Buddy.bat`.

Buddy opens borderless on the whole monitor. The 1280x720 frame scales up to fit. On a 1920x1080 screen that is exactly the 1080p layout. A monitor that is not 16:9 gets black bars around the frame.

- The center opening is a dark screen that says nothing until a game is running. The words `Load a game` sit in Buddy's box, under his head, not on the game picture.
- When RetroArch or EmulationStation is open, the opening goes clear so the game shows through (Windows only). Buddy places that window once. It does not keep shoving windows around.
- Buddy's hologram sits in the bottom-right box, resting left toward the game, with the ring under his chin. The name on screen stays whatever `character_name` says.
- The menu is the button bar under that box. It is not a top-right button. The buttons are Buddy (Male / Female), Mode (casual, sassy, extreme), Voice, Settings (resting direction), Sound, and Full/Window.
- F8 focuses that menu. Arrow keys and Enter move through it. F11 toggles fullscreen and a 1280x720 window.
- F9 is push-to-talk. Hold it, talk, let go. On Windows those keys are global, so they still work while the game is in front.
- Ctrl+Shift+Q quits. Closing the black console window quits too, including the local API.
- The overlay does not draw screenshots. Capture is only for vision, only of the game window, and only about once a second.

Open your game from EmulationStation or RetroArch, then start Buddy.
The frame follows the system that is running (NES, Super NES, or Genesis) when Buddy can tell. There is no menu button that swaps frames.

## 6. Talk to him

Hold F9 and say these, or send them to the local API:

- `switch to extreme`
- `stop insulting me`
- `what am I playing`
- `open RetroArch`
- `clear memory`

If a program did not start, the line says he did not launch it. That is the real result.

## 7. If something fails

- `install.bat` closes immediately: install Python and check PATH.
- The window opens but the game is covered, or the picture sits outside the hole: RetroArch is exclusive fullscreen, or the window size does not match the append-config. Use the windowed-fullscreen cfg from install (the size is in the filename) and start Buddy again.
- The overlay shrinks, flickers, or turns pink: that was Buddy moving its own window into the game hole. Quit with Ctrl+Shift+Q or close the console. Current builds refuse to move Buddy's window and do not draw captured frames on the overlay. If it still happens, the log under `%LOCALAPPDATA%\VideoGameWingman\buddy.log` will say `Safety stop`.
- He does not speak: Windows voice needs this PC. Pick a device in the menu after you read STREAMING.md. Volume 0 and Mute both keep him quiet on purpose.
- The microphone errors: another app has the mic, or the voice packages did not install. Run install.bat again and read the red text.
- A log is written under `%LOCALAPPDATA%\VideoGameWingman\buddy.log` unless you set `data_dir` in the config.
