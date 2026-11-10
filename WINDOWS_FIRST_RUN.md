# First run on Windows

You need Windows 10 or 11 and Python 3.11 or newer.
Buddy was built on a Linux machine. The steps below are what you run on your PC.
Voice, the microphone, the transparent overlay, and emulator windows still need you to try them there.

## One-download installer

On a Windows build machine, run `packaging\build-windows.ps1`. It downloads RetroArch 1.22.1, an embedded Python 3.12.8, and the Visual C++ runtime, checks checksums, and compiles `dist\Buddy-Setup.exe` with Inno Setup 6.

That installer is per-user. It does not ask for an administrator password. It adds Start menu and Desktop shortcuts, a Repair shortcut, and an uninstaller. Logs go to `%LOCALAPPDATA%\Buddy\logs`.

The first launch is the setup wizard: install or adopt RetroArch, a Buddy Games folder for ROMs you already own, overlays, Casual/Sassy/Extreme, an optional API key stored in Windows Credential Manager, then Male or Female. Play opens Buddy and puts RetroArch in the screen hole.

Buddy does not download ROMs. Snes9x, PicoDrive, and Genesis Plus GX are not installed. See [LICENSES.md](LICENSES.md).

Code signing and a license key are hooks only. They are not active.

The steps below are for a source checkout, which still starts with Python.

## 1. Install Python

1. Open https://www.python.org/downloads/windows/
2. Download Python 3.11 or newer.
3. Run the installer.
4. Check **Add python.exe to PATH**.
5. Finish the install.

## 2. Start Buddy

1. Copy this project folder onto the PC (or clone the repo).
2. Double-click `Start-Buddy.bat`.

That one double-click opens Buddy and RetroArch. The game window is placed in the screen hole. You do not start RetroArch first, and you do not stretch it. Details are in section 4.

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

## 4. RetroArch opens with Buddy

Double-click `Start-Buddy.bat`. That is the whole start.

Buddy opens borderless on the whole monitor and launches RetroArch into the screen hole. You do not start RetroArch yourself, and you do not stretch its window.

Buddy looks for `retroarch.exe` in this order: the path in `config/buddy.config.json`, then `C:\RetroArch-Win64`, Program Files, `%APPDATA%\RetroArch`, Steam's `steamapps\common\RetroArch`, a Scoop install, the registry, and PATH. The first one it finds is saved back to the config.

If none of those exist, Buddy's box says `RetroArch was not found` and shows a **Find RetroArch** button. That button stays in Buddy's box. It is never drawn over the game. Pick `retroarch.exe` and Buddy launches it.

RetroArch opens borderless, at the hole's real pixel position and size. Integer scale is off, and the picture fills the hole. A ROM and core are passed only when `retroarch.rom` and `retroarch.core` are set. Otherwise RetroArch's menu opens inside the hole.

```json
"retroarch": {
  "path": "",
  "rom": "",
  "core": "",
  "close_on_quit": false
}
```

`close_on_quit` stays false, so quitting Buddy leaves RetroArch open. Set it to true only if Buddy should close a RetroArch it started.

ROM folders are optional. They are for "load this game" later, not for the first double-click:

```json
"libraries": [
  { "system": "snes", "path": "C:\\ROMs\\SNES", "core": "C:\\RetroArch\\cores\\snes9x_libretro.dll" }
]
```

- The 1280x720 frame scales up to fit. On a 1920x1080 screen that is the 1080p layout. A monitor that is not 16:9 gets black bars around the frame.
- Until RetroArch's window is up, the opening is a dark screen. Words stay in Buddy's box, under his head.
- When that window is up, the opening goes clear (Windows only) and clicks pass through to the game. If RetroArch moves, Buddy puts it back. It does not move its own window.
- If RetroArch was already open, Buddy uses that window instead of starting a second one.
- Buddy's hologram sits in the bottom-right box, resting left toward the game, with the ring under his chin. The name on screen stays whatever `character_name` says.
- The menu is the button bar under that box. The buttons are Buddy (Male / Female), Mode (casual, sassy, extreme), Voice, Settings (resting direction), Sound, and Full/Window.
- F8 focuses that menu. Arrow keys and Enter move through it. F11 toggles fullscreen and a 1280x720 window.
- F9 is push-to-talk. Hold it, talk, let go. On Windows those keys are global, so they still work while the game is in front.
- Ctrl+Shift+Q quits. Closing the black console window quits too, including the local API. RetroArch keeps running.
- The overlay does not draw screenshots. Capture is only for vision, only of the game window, and only about once a second.

The frame follows the system that is running (NES, Super NES, or Genesis) when Buddy can tell. There is no menu button that swaps frames.

The log under `%LOCALAPPDATA%\VideoGameWingman\buddy.log` records the path, the launch arguments, the hwnd, and both rectangles.

## 5. Talk to him

Hold F9 and say these, or send them to the local API:

- `switch to extreme`
- `stop insulting me`
- `what am I playing`
- `open RetroArch`
- `clear memory`

If a program did not start, the line says he did not launch it. That is the real result.

## 6. If something fails

- `install.bat` closes immediately: install Python and check PATH.
- The window opens but the game is covered, or the picture sits outside the hole: look in `buddy.log` for `Screen hole rect` and `SetWindowPos`. RetroArch should be the borderless window Buddy launched, not exclusive fullscreen. Start Buddy again with `Start-Buddy.bat` so it can place the window.
- The overlay shrinks, flickers, or turns pink: that was Buddy moving its own window into the game hole. Quit with Ctrl+Shift+Q or close the console. Current builds refuse to move Buddy's window and do not draw captured frames on the overlay. If it still happens, the log under `%LOCALAPPDATA%\VideoGameWingman\buddy.log` will say `Safety stop`.
- He does not speak: Windows voice needs this PC. Pick a device in the menu after you read STREAMING.md. Volume 0 and Mute both keep him quiet on purpose.
- The microphone errors: another app has the mic, or the voice packages did not install. Run install.bat again and read the red text.
- A log is written under `%LOCALAPPDATA%\VideoGameWingman\buddy.log` unless you set `data_dir` in the config.
