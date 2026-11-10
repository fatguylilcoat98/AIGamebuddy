"""Windows smoke helpers. Called as a file so PowerShell does not eat quotes."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _user32():
    import ctypes
    return ctypes.windll.user32


def hide_consoles() -> None:
    """The runner's own PowerShell window must not cover the overlay."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    classes = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, 256)
        if name.value in {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"}:
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            classes.append(name.value)
        return True

    user32.EnumWindows(visit, 0)
    print(f"minimized consoles {len(classes)}")


def raise_overlay() -> None:
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    hwnd = user32.FindWindowW(None, "Buddy Overlay")
    if not hwnd:
        print("Buddy Overlay window was not found to raise")
        return
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    # HWND_TOPMOST, keep the size the overlay already chose.
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
    user32.SetForegroundWindow(hwnd)
    print(f"raised Buddy Overlay hwnd={hwnd}")


def grab(path: Path) -> None:
    from PIL import ImageGrab
    if os.environ.get("BUDDY_FRAME_SHOT") == "1":
        hide_consoles()
        raise_overlay()
        time.sleep(0.6)
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


def close_window(title: str) -> None:
    user32 = _user32()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        print(f"close: {title} was already gone")
        return
    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    print(f"closed hwnd={hwnd} title={title}")


def prove(path: Path, menu_open: bool) -> None:
    from PIL import Image
    from backend.frame_proof import prove_snes_screen
    problems = prove_snes_screen(
        Image.open(path),
        menu_open=menu_open,
        menu_scrolled=os.environ.get("BUDDY_MENU_BOTTOM") == "1",
    )
    for item in problems:
        print(item)
    if problems:
        raise SystemExit("pixel check failed")
    print(f"pixel check ok menu_open={menu_open}")


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "close":
        close_window(os.environ.get("BUDDY_WINDOW_TITLE") or "Buddy Setup")
        return 0
    if command == "prove":
        prove(Path(os.environ["BUDDY_SHOT"]), os.environ.get("BUDDY_MENU_OPEN") == "1")
        return 0
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
