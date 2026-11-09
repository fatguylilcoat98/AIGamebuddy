# Art files

The old hologram photo and `Retro_Arcade_Replay_Menu_RetroArch_Fix(1).zip` are not in this repository, its branches, or its history. They were not used.

The concept screenshots Chris sent are layout references only. They contain console logos and the old face. They are not shipped.

What is in the repo is original pixel art drawn by the frame generator, plus a new cartoon hologram:

- `assets/previews/frame-nes.png`
- `assets/previews/frame-snes.png`
- `assets/previews/frame-genesis.png`
- `assets/previews/frame-*-opening.png` shows the game opening on a checkerboard so you can see it is empty
- `assets/previews/buddy-expressions.png`
- `assets/previews/buddy-idle.gif`
- `assets/previews/buddy-talk.gif`

The app draws these at runtime from `backend/frames.py` and `backend/hologram.py`. You do not have to drop files in for the current look.

The banner text comes from `banner_title` in the config. The default is `GAME WINGMAN`. The name plate says BUDDY.

Do not replace these with the concept images. Those include trademarks and the face that must not ship.

## What you still need to provide

Nothing visual is blocking a first Windows test. These are the non-art gaps:

- A Meta API key in `BUDDY_META_API_KEY` if provider is `meta`, plus the real model name
- A vision key in `BUDDY_VISION_API_KEY` and a vision model name, if you want him to watch the screen
- Ollama running locally if provider is `ollama`
- RetroArch and EmulationStation paths, and ROM folders, if you want him to launch games
- A microphone and speakers (or a virtual audio cable) on the Windows PC
