# Verification

Run on this machine: `python3 -m pytest tests -q` — 25 passed.
That does not mean the Windows overlay, microphone, or a live model was tried.
A feature is listed from what the code does and what the tests check, not from a wish list.

## Implemented and tested

Tested here with pytest. No Windows desktop, microphone, or API key was available.

- Personality packs load from `data/personalities/{casual,sassy,extreme}/` (`STYLE.md`, `seeds.json`, `templates.json`) and the loader rejects a broken pack.
- Angle lists are read from `ANTI-REPETITION.md` (20 categories, including `faceplant`, `tadpole`, `reset_spicy`).
- Seeds are not played back. A line is spoken from a template only when every `{slot}` is a known fact. The test checks a death count fills `{count}` and the result is not a seed line.
- Similarity catches "you suck at jumping" and "you're terrible at jumping".
- Metaphor families block the tadpole/snack-fish group and the "you suck" group.
- Same angle is not reused back to back. A category has a short cooldown. An exact callback is blocked the second time. A new callback may refer to an older event.
- "Stop insulting me" is stored and the next roast is replaced with a plain line.
- Opening RetroArch with no path returns a failure and the message says it did not launch.
- Takeover stays off when the config flag is off, when the title looks online, and even when Street Fighter II is approved: the result says no input was sent.
- Memory reset keeps joke history. Clear deletes it. A second session still sees the saved personality and an observed event.
- Window titles are reported as titles, not as "I can see the game." On a non-Windows host the detector says detection needs Windows.
- The three frames are 1920x1080 PNG files. The game opening is alpha 0. The menu and frame are opaque. Drawn labels do not include Sega, Nintendo, Sonic, Mario, or Zion.
- Official GB-cap sheets are sliced into front expressions and turn poses. Black becomes transparent. Male turn panels face left and stay unmirrored. Female turn panels face right, so her left-facing set is mirrored and the cap letters are redrawn upright (not reversed). Idle sweeps left and right around a resting direction (default left, toward the game). Talk and reactions face the camera. Mouth level swaps the closed and open talk frames. Male and female are separate sprite sets. The display name stays Buddy.
- Config comments are allowed. A character name of Zion is renamed to Buddy. The sample config has no API key.
- Ollama requests are built for localhost. A bad HTTP URL is rejected. A fake 401 error has the key redacted.
- The old short-term cooldown in `BuddyBrain` still blocks chatter a few seconds after a line.

## Implemented but not yet tested on Windows

The code is in the app. It was not run on Windows, with a mic, with OBS, or with RetroArch.

- `install.bat` / `install.ps1`, `Start-Buddy.bat`, and the `.venv` they create.
- The tkinter overlay, hamburger menu, F9 push-to-talk, and Ctrl+Shift+Q.
- Per-pixel hole and click-through (`SetWindowRgn`) and moving the emulator window into the opening.
- Windows System.Speech to a WAV, then playback on a chosen output device and volume.
- Microphone capture and local Whisper transcription (`BuddyEars`).
- Screen capture and a real vision API call. `parse_vision_text` is unit-tested for plain text, a confident JSON event, and a low-confidence event. No live vision model was called.
- Ollama or Meta on a real network. Tests use a fake HTTP transport.
- DPI awareness and a 1280x720 top-most window over a real emulator.

## Experimental

- Takeover and co-op gates for Street Fighter II (offline), a fishing title, Double Dragon, Contra, and TMNT. Permission can open. No buttons are sent. There is no gameplay AI.
- RetroArch `MENU_TOGGLE` over UDP, only if `retroarch.command_enabled` is true. The send result is whatever the socket does. It was not tried against RetroArch.
- Compact streaming layout. The window code switches size. OBS capture of a transparent window was not tried.
- Vision event names and confidence. Low confidence is treated as unknown. No model was benchmarked.

## Not yet implemented

- Wake word. The config flag is ignored except for a log line. Use F9.
- Actually playing a game, including Street Fighter II versus the CPU and player-2 co-op.
- Modern PC games and capture-card consoles.
- A license, serial, or paid download.
- Dragging or calibrating the overlay. Position is fixed on purpose.

## Blocked by missing assets, credentials, or hardware

- Meta chat and vision keys, and the exact model names that work with your account.
- Confirmation that `https://api.meta.ai/v1` is the right host. It is only the default.
- Ollama installed on the Windows PC if you choose the local provider.
- Your RetroArch / EmulationStation paths and ROM folders.
- A microphone, speakers or a virtual cable, and OBS on that PC.
- Nothing visual is blocking a first look. The expression and turn sheets Chris supplied are in `assets/hologram/source/`. The full concept board with game characters is not in the repo.
