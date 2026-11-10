"""Windows smoke helpers. Called as a file so PowerShell does not eat quotes."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def grab(path: Path) -> None:
    from PIL import ImageGrab
    image = ImageGrab.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, quality=90)
    print(f"shot {path} {image.size}")


def wait_window(title: str, path: Path, timeout: float) -> None:
    import ctypes
    user32 = ctypes.windll.user32
    deadline = time.time() + timeout
    hwnd = 0
    while time.time() < deadline:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            break
        time.sleep(0.4)
    if not hwnd:
        raise SystemExit(f"window not found: {title}")
    user32.ShowWindow(hwnd, 9)
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(1.0)
    grab(path)
    print(f"window hwnd={hwnd} title={title} shot={path}")


def compare(game_path: Path, menu_path: Path) -> None:
    from PIL import Image
    game = Image.open(game_path).convert("RGB")
    menu = Image.open(menu_path).convert("RGB")
    width, height = game.size
    points = (
        (width // 2, height // 2),
        (width // 2, height // 3),
        (width // 2, (2 * height) // 3),
    )
    deltas = []
    for x, y in points:
        a = game.getpixel((x, y))
        b = menu.getpixel((x, y))
        delta = sum(abs(int(a[i]) - int(b[i])) for i in range(3))
        deltas.append(delta)
        print(f"pixel {x},{y} game={a} menu={b} delta={delta}")
    if max(deltas) < 30:
        raise SystemExit("RetroArch menu did not change the picture in the Super NES opening")


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "window":
        title = os.environ.get("BUDDY_WINDOW_TITLE") or "Buddy Setup"
        out = Path(os.environ["BUDDY_SHOT"])
        timeout = float(os.environ.get("BUDDY_WINDOW_TIMEOUT") or "20")
        wait_window(title, out, timeout)
        return 0
    if command == "grab":
        grab(Path(os.environ["BUDDY_SHOT"]))
        return 0
    if command == "compare":
        compare(Path(os.environ["BUDDY_GAME_SHOT"]), Path(os.environ["BUDDY_MENU_SHOT"]))
        return 0
    print("usage: smoke_windows.py window|grab|compare", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
