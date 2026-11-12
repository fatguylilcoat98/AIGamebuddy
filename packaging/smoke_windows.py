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


def prove_lines(path: Path) -> None:
    from datetime import datetime
    if os.environ.get("BUDDY_EXPECT_SILENT") == "1":
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if "missed that screen" in text.lower():
            raise SystemExit("the missed-screen fallback was spoken")
        rows = [
            line for line in text.splitlines()
            if "\tsource=" in line and line.split("\t")[-1].strip()
        ]
        if rows:
            raise SystemExit(f"Buddy spoke {len(rows)} local lines")
        print("local speech stayed quiet: ok")
        return
    rows = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if any(tag in line for tag in ("\tsource=frame", "\tsource=vision", "\tsource=follow", "\tsource=template", "\tsource=llm"))
    ]
    print(f"frame lines {len(rows)}")
    if len(rows) < 8:
        raise SystemExit(f"only {len(rows)} frame comments, wanted at least 8")
    texts = {row.split("\t", 3)[-1] for row in rows}
    if len(texts) < 6:
        raise SystemExit("the frame comments did not vary")
    stamps = [datetime.strptime(row.split("\t", 1)[0], "%Y-%m-%dT%H:%M:%SZ") for row in rows]
    span = (max(stamps) - min(stamps)).total_seconds()
    print(f"frame comments span {span:.0f}s unique {len(texts)}")
    if span < 150:
        raise SystemExit(f"frame comments only span {span:.0f}s, wanted 3 minutes")


def prove_repeats(path: Path) -> None:
    """Exact repeats and the near-duplicate rate across the spoken log."""
    from backend.novelty import similarity
    from backend.said_history import NEAR_DUP
    rows = [
        line.split("\t", 3)[-1].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if "\tsource=" in line and not line.endswith("\t")
    ]
    rows = [row for row in rows if row]
    exact = 0
    near_pairs = 0
    pairs = 0
    for index, line in enumerate(rows):
        for earlier in rows[:index]:
            pairs += 1
            if " ".join(line.lower().split()) == " ".join(earlier.lower().split()):
                exact += 1
            elif similarity(line, earlier) >= NEAR_DUP:
                near_pairs += 1
    rate = (near_pairs / pairs) if pairs else 0.0
    report = (
        f"spoken={len(rows)}\nexact_repeats={exact}\nnear_dup_pairs={near_pairs}\n"
        f"comparisons={pairs}\nnear_dup_rate={rate:.4f}\n"
    )
    print(report)
    out = os.environ.get("BUDDY_REPEAT_OUT")
    if out:
        Path(out).write_text(report, encoding="utf-8")
    if exact:
        raise SystemExit(f"{exact} exact repeated lines")
    if len(rows) >= 8 and rate > 0.12:
        raise SystemExit(f"near-duplicate rate {rate:.2f} is too high")


def prove_attitudes(script: Path, out: Path) -> None:
    """Same frames, three attitudes. The tones have to read as different people."""
    from backend.game_watch import GameWatch
    from backend.novelty import similarity
    from backend.personas import curses_in
    frames = [line.strip() for line in script.read_text(encoding="utf-8").splitlines() if line.strip()]
    blocks = []
    loss = {}
    comeback = {}
    for personality in ("casual", "sassy", "extreme"):
        watch = GameWatch()
        lines = []
        for frame in frames:
            watch.update(frame)
            spoken, _source = watch.comment(personality)
            lines.append(spoken)
        blocks.append(f"[{personality}]\n" + "\n".join(lines))
        blob = "\n".join(lines).lower()
        loss[personality] = next(line for line in lines if "round 1" in line.lower() and "lost" in line.lower())
        comeback[personality] = next(line for line in lines if "comeback" in line.lower())
        stats = watch.said.repetition()
        if stats["exact_repeats"]:
            raise SystemExit(f"{personality} repeated a line")
        if personality == "casual" and curses_in(blob):
            raise SystemExit("casual cursed")
        if personality == "sassy" and any(word in blob for word in ("fuck", "shit")):
            raise SystemExit("sassy was not clean-ish")
        if personality == "extreme" and "fuck" not in blob:
            raise SystemExit("extreme did not curse")
    for left, right in (("casual", "sassy"), ("sassy", "extreme"), ("casual", "extreme")):
        if similarity(loss[left], loss[right]) >= 0.55:
            raise SystemExit(f"{left} and {right} loss lines are too alike")
        if similarity(comeback[left], comeback[right]) >= 0.55:
            raise SystemExit(f"{left} and {right} comeback lines are too alike")
    text = "\n\n".join(blocks) + "\n"
    out.write_text(text, encoding="utf-8")
    print(text)


def prove(path: Path, menu_open: bool) -> None:
    from PIL import Image
    from backend.frame_proof import prove_snes_screen
    image = Image.open(path)
    expected = os.environ.get("BUDDY_EXPECT_SIZE", "").lower()
    if expected:
        want = tuple(int(part) for part in expected.split("x"))
        if image.size != want:
            print(f"screenshot is {image.size[0]}x{image.size[1]}, wanted {expected}")
            raise SystemExit("pixel check failed")
    problems = prove_snes_screen(
        image,
        menu_open=menu_open,
        menu_scrolled=os.environ.get("BUDDY_MENU_BOTTOM") == "1",
        expect_game=os.environ.get("BUDDY_EXPECT_GAME") == "1",
    )
    for item in problems:
        print(item)
    if problems:
        raise SystemExit("pixel check failed")
    print(f"pixel check ok menu_open={menu_open}")


def buddy_consoles() -> int:
    """Fail when Buddy itself opened a console. The runner's own windows are ignored."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, 256)
        if name.value != "ConsoleWindowClass":
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, int(pid.value))
        path = ""
        if handle:
            buf = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(520)
            if kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                path = buf.value
            kernel.CloseHandle(handle)
        lowered = path.lower()
        if "\\buddy\\" in lowered and lowered.endswith("python.exe"):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            found.append(f"console pid={pid.value} path={path} title={title.value}")
        return True

    user32.EnumWindows(visit, 0)
    for line in found:
        print(line)
    if found:
        return 1
    print("buddy consoles 0")
    return 0


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "lines":
        prove_lines(Path(os.environ["BUDDY_LINES"]))
        return 0
    if command == "repeats":
        prove_repeats(Path(os.environ["BUDDY_LINES"]))
        return 0
    if command == "attitudes":
        prove_attitudes(Path(os.environ["BUDDY_FRAME_SCRIPT"]), Path(os.environ["BUDDY_ATTITUDES"]))
        return 0
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
    if command == "consoles":
        return buddy_consoles()
    if command == "compare":
        compare(Path(os.environ["BUDDY_GAME_SHOT"]), Path(os.environ["BUDDY_MENU_SHOT"]))
        return 0
    print("usage: smoke_windows.py window|grab|compare", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
