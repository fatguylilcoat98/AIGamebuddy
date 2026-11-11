"""Overlay and emulator window geometry.

Moving a real window is Windows-only. On any other system the call reports
that it did not move anything. Buddy never moves its own window: that shrinks
the overlay into its own game hole and looks like an infinite mirror.
"""
from __future__ import annotations

import logging
import os

from .capture_safety import OVERLAY_SIZE, clamp_overlay_geometry
from .game_session import EMULATORS
from .layout_spec import HOLE, OUTPUT_H, OUTPUT_W, scale_rect
from .results import ActionResult

log = logging.getLogger("buddy.layout")

# Win10 2004+. Hides the window from screen capture.
WDA_EXCLUDEFROMCAPTURE = 0x00000011
# Older fallback: capture shows a black rectangle instead of the window.
WDA_MONITOR = 0x00000001


def hole_on_screen(origin_x: int, origin_y: int, window_w: int, window_h: int) -> tuple[int, int, int, int]:
    x, y, w, h = scale_rect(HOLE, window_w, window_h)
    return origin_x + x, origin_y + y, w, h


def emulator_target(overlay_origin: tuple[int, int], overlay_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Screen rectangle where the emulator should sit so it fills the game opening."""
    return hole_on_screen(overlay_origin[0], overlay_origin[1], overlay_size[0], overlay_size[1])


def select_emulator_hwnd(windows: list[tuple[int, str]], own_hwnds: set[int]) -> int | None:
    """Pick a RetroArch or EmulationStation window. Never one of Buddy's own."""
    for hwnd, executable in windows:
        if not hwnd or int(hwnd) in own_hwnds:
            continue
        name = (executable or "").lower()
        if name in EMULATORS or "retroarch" in name or "emulationstation" in name:
            return int(hwnd)
    return None


def position_hwnd(hwnd: int, rect: tuple[int, int, int, int], own_hwnds: set[int] | None = None) -> ActionResult:
    """Move one known emulator window. Refuses Buddy's hwnd even if it is in front."""
    if os.name != "nt":
        return ActionResult(False, "Positioning the emulator window requires Windows, so I did not move it.",
                            reason="not_windows")
    forbidden = own_hwnds or set()
    if not hwnd or int(hwnd) in forbidden:
        return ActionResult(
            False,
            "That window is Buddy's overlay, so I did not move it.",
            reason="own_window",
        )
    return _set_window_pos(int(hwnd), rect)


def position_foreground_window(rect: tuple[int, int, int, int]) -> ActionResult:
    """Old entry point. It no longer moves whatever happens to be in front.

    Moving the foreground window pulled Buddy into its own hole, then other apps.
    """
    if os.name != "nt":
        return ActionResult(False, "Positioning the emulator window requires Windows, so I did not move it.",
                            reason="not_windows")
    return ActionResult(
        False,
        "I did not move the foreground window. Only a RetroArch or EmulationStation window can be placed.",
        reason="foreground_refused",
    )


def _set_window_pos(hwnd: int, rect: tuple[int, int, int, int]) -> ActionResult:
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        x, y, w, h = rect
        flags = 0x0040  # SWP_SHOWWINDOW
        # HWND_NOTOPMOST. The overlay is topmost, so the game stays under the bezel.
        moved = bool(user32.SetWindowPos(int(hwnd), ctypes.c_void_p(-2), int(x), int(y), int(w), int(h), flags))
        if not moved:
            return ActionResult(False, "Windows refused to move the emulator window, so I left it where it was.",
                                reason="set_window_failed")
        snap_client_area(int(hwnd), rect)
        return ActionResult(True, "Moved the emulator window into the game opening.",
                            reason="moved", data={"rect": [x, y, w, h], "hwnd": hwnd})
    except Exception as exc:
        return ActionResult(False, f"I could not move the window. {exc}", reason="window_error")


def client_screen_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Client area in screen pixels. The menu bar is outside this rectangle."""
    if os.name != "nt" or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        rect = RECT()
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
        user32.ClientToScreen.restype = wintypes.BOOL
        if not user32.GetClientRect(int(hwnd), ctypes.byref(rect)):
            return None
        origin = POINT(0, 0)
        if not user32.ClientToScreen(int(hwnd), ctypes.byref(origin)):
            return None
        return (
            int(origin.x), int(origin.y),
            int(rect.right - rect.left), int(rect.bottom - rect.top),
        )
    except Exception as exc:
        log.warning("GetClientRect failed for %s: %s", hwnd, exc)
        return None


def snap_client_area(hwnd: int, target: tuple[int, int, int, int]) -> str:
    """Move the outer window so its client area is exactly `target`."""
    if os.name != "nt" or not hwnd:
        return "not_windows"
    outer = window_rect(hwnd)
    client = client_screen_rect(hwnd)
    if outer is None or client is None:
        return "unmeasured"
    tx, ty, tw, th = (int(v) for v in target)
    ox, oy, ow, oh = outer
    cx, cy, cw, ch = client
    if cw < 1 or ch < 1:
        return "empty"
    nx = ox + (tx - cx)
    ny = oy + (ty - cy)
    nw = ow + (tw - cw)
    nh = oh + (th - ch)
    if (nx, ny, nw, nh) == outer:
        return "exact"
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        ok = bool(user32.SetWindowPos(int(hwnd), ctypes.c_void_p(-2), int(nx), int(ny), int(nw), int(nh), 0x0040))
        return "snapped" if ok else "failed"
    except Exception as exc:
        log.warning("Could not snap the client area: %s", exc)
        return "failed"


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Outer window rectangle as x, y, width, height. None off Windows."""
    if os.name != "nt" or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        rect = wintypes.RECT()
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        if not user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
            return None
        return (
            int(rect.left), int(rect.top),
            int(rect.right - rect.left), int(rect.bottom - rect.top),
        )
    except Exception as exc:
        log.warning("GetWindowRect failed for %s: %s", hwnd, exc)
        return None


def strip_window_decorations(hwnd: int) -> str:
    """Drop the title bar so the window size is the game, not the frame around it."""
    if os.name != "nt" or not hwnd:
        return "not_windows"
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        pointer = ctypes.sizeof(ctypes.c_void_p) == 8
        get_long = user32.GetWindowLongPtrW if pointer else user32.GetWindowLongW
        set_long = user32.SetWindowLongPtrW if pointer else user32.SetWindowLongW
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong if pointer else ctypes.c_long]
        get_long.restype = ctypes.c_longlong if pointer else ctypes.c_long
        set_long.restype = ctypes.c_longlong if pointer else ctypes.c_long
        style_index = -16  # GWL_STYLE
        caption = 0x00C00000
        thick = 0x00040000
        border = 0x00800000
        dialog = 0x00400000
        sysmenu = 0x00080000
        overlapped = 0x00CF0000
        popup = 0x80000000
        style = int(get_long(int(hwnd), style_index))
        cleaned = (style & ~caption & ~thick & ~border & ~dialog & ~sysmenu & ~overlapped) | popup
        if style & 0x10000000:  # WS_VISIBLE
            cleaned |= 0x10000000
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.GetMenu.argtypes = [wintypes.HWND]
        user32.GetMenu.restype = wintypes.HMENU
        menu = user32.GetMenu(int(hwnd))
        changed = cleaned != style or bool(menu)
        if cleaned != style:
            set_long(int(hwnd), style_index, cleaned)
        # The GDI driver draws File / Command / Window even after the frame is gone.
        user32.SetMenu.argtypes = [wintypes.HWND, wintypes.HMENU]
        user32.SetMenu.restype = wintypes.BOOL
        user32.SetMenu(int(hwnd), None)
        user32.DrawMenuBar.argtypes = [wintypes.HWND]
        user32.DrawMenuBar.restype = wintypes.BOOL
        user32.DrawMenuBar(int(hwnd))
        if changed:
            # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
            user32.SetWindowPos(int(hwnd), ctypes.c_void_p(0), 0, 0, 0, 0, 0x0020 | 0x0004 | 0x0002 | 0x0001)
        return "stripped" if changed else "already_borderless"
    except Exception as exc:
        log.warning("Could not remove decorations on %s: %s", hwnd, exc)
        return "failed"


def visible_hwnd_for_pid(pid: int) -> int | None:
    """Largest visible top-level window owned by `pid`. Used when the class name is odd."""
    if os.name != "nt" or not pid:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

        best = [0, 0]

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if int(owner.value) != int(pid):
                return True
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            area = max(0, int(rect.right) - int(rect.left)) * max(0, int(rect.bottom) - int(rect.top))
            if area > best[0]:
                best[0] = area
                best[1] = int(hwnd)
            return True

        user32.EnumWindows(visit, 0)
        return int(best[1]) or None
    except Exception as exc:
        log.warning("Could not find a window for pid %s: %s", pid, exc)
        return None


def list_window_details() -> list[tuple[int, str, str]]:
    """(hwnd, executable, class name) for visible top-level windows."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        found: list[tuple[int, str, str]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            executable = ""
            if pid.value:
                handle = kernel32.OpenProcess(0x1000, False, pid.value)
                if handle:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = wintypes.DWORD(len(buffer))
                        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                            executable = os.path.basename(buffer.value).lower()
                    finally:
                        kernel32.CloseHandle(handle)
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            found.append((int(hwnd), executable, str(class_name.value)))
            return True

        user32.EnumWindows(visit, 0)
        return found
    except Exception as exc:
        log.warning("Could not list window classes: %s", exc)
        return []


def list_toplevel_windows() -> list[tuple[int, str]]:
    """(hwnd, executable) for visible top-level windows. Empty off Windows."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        found: list[tuple[int, str]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            executable = ""
            if pid.value:
                handle = kernel32.OpenProcess(0x1000, False, pid.value)
                if handle:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = wintypes.DWORD(len(buffer))
                        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                            executable = os.path.basename(buffer.value).lower()
                    finally:
                        kernel32.CloseHandle(handle)
            found.append((int(hwnd), executable))
            return True

        user32.EnumWindows(visit, 0)
        return found
    except Exception as exc:
        log.warning("Could not list windows: %s", exc)
        return []


_BLUE_HWND = 0
_BLUE_WNDPROC = None


def place_blue_backing(rect: tuple[int, int, int, int]) -> int:
    """A blue popup behind the game and under the topmost frame.

    The overlay art is drawn on top of the extra pixels, so the blue tucks
    under the painting. RetroArch is placed after this and stays above it.
    """
    global _BLUE_HWND
    if os.name != "nt":
        return 0
    x, y, w, h = (int(v) for v in rect)
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        if not _BLUE_HWND or not user32.IsWindow(_BLUE_HWND):
            global _BLUE_WNDPROC
            class_name = "BuddyBlueBacking"

            def _proc(hwnd, msg, wp, lp):
                return user32.DefWindowProcW(hwnd, msg, wp, lp)

            _BLUE_WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            )(_proc)
            wind = wintypes.WNDCLASSW()
            wind.lpfnWndProc = _BLUE_WNDPROC
            wind.lpszClassName = class_name
            wind.hbrBackground = gdi32.CreateSolidBrush(0x00DC2800)  # RGB(0, 40, 220)
            wind.hInstance = ctypes.WinDLL("kernel32").GetModuleHandleW(None)
            user32.RegisterClassW(ctypes.byref(wind))
            user32.CreateWindowExW.argtypes = [
                wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
            ]
            user32.CreateWindowExW.restype = wintypes.HWND
            _BLUE_HWND = int(user32.CreateWindowExW(
                0, class_name, "Buddy blue",
                0x80000000 | 0x10000000,  # WS_POPUP | WS_VISIBLE
                x, y, w, h, 0, 0, wind.hInstance, 0,
            ) or 0)
        # HWND_BOTTOM so the game window, placed next, sits above the blue.
        user32.SetWindowPos(int(_BLUE_HWND), ctypes.c_void_p(1), x, y, w, h, 0x0040)
        return int(_BLUE_HWND)
    except Exception as exc:
        log.warning("Could not place the blue backing: %s", exc)
        return 0


def raise_overlay_front(hwnd: int, width: int, height: int, origin: tuple[int, int] = (0, 0)) -> str:
    """Fullscreen, borderless, and above every other window, including consoles."""
    if os.name != "nt" or not hwnd:
        return "not_windows"
    hwnd = toplevel_hwnd(hwnd)
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        # HWND_TOPMOST, SWP_SHOWWINDOW
        ok = bool(user32.SetWindowPos(
            int(hwnd), ctypes.c_void_p(-1),
            int(origin[0]), int(origin[1]), int(width), int(height), 0x0040,
        ))
        return "raised" if ok else "failed"
    except Exception as exc:
        log.warning("Could not raise the overlay: %s", exc)
        return "failed"


def exclude_window_from_capture(hwnd: int) -> str:
    """Keep this window out of screenshots. Returns the affinity that stuck."""
    if os.name != "nt" or not hwnd:
        return "not_windows"
    hwnd = toplevel_hwnd(hwnd)
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
        if user32.SetWindowDisplayAffinity(int(hwnd), WDA_EXCLUDEFROMCAPTURE):
            return "exclude"
        log.warning(
            "SetWindowDisplayAffinity WDA_EXCLUDEFROMCAPTURE failed on hwnd %s (error %s). Trying WDA_MONITOR.",
            hwnd, ctypes.get_last_error(),
        )
        if user32.SetWindowDisplayAffinity(int(hwnd), WDA_MONITOR):
            return "monitor"
        log.warning(
            "SetWindowDisplayAffinity WDA_MONITOR also failed on hwnd %s (error %s).",
            hwnd, ctypes.get_last_error(),
        )
        return "failed"
    except Exception as exc:
        log.warning("Could not exclude hwnd %s from capture: %s", hwnd, exc)
        return "failed"


def toplevel_hwnd(hwnd: int) -> int:
    """Tk's winfo_id is often a child. Region and capture calls need the outer window."""
    if os.name != "nt" or not hwnd:
        return int(hwnd or 0)
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        root = user32.GetAncestor(wintypes.HWND(int(hwnd)), 2)  # GA_ROOT
        return int(root) if root else int(hwnd)
    except Exception:
        return int(hwnd)


def apply_hole_region(hwnd: int, width: int, height: int, hole: tuple[int, int, int, int],
                      keep: tuple[tuple[int, int, int, int], ...] = ()) -> ActionResult:
    """Cut the game opening out of a window so clicks pass through. Windows only.

    `keep` rectangles stay part of the window. The hamburger and Buddy's box
    are passed here so a running game cannot swallow those clicks.
    """
    if os.name != "nt":
        return ActionResult(False, "Click-through overlay holes require Windows.", reason="not_windows")
    hwnd = toplevel_hwnd(hwnd)
    try:
        import ctypes
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        full = gdi32.CreateRectRgn(0, 0, int(width), int(height))
        hx, hy, hw, hh = hole
        cut = gdi32.CreateRectRgn(int(hx), int(hy), int(hx + hw), int(hy + hh))
        for rect in keep:
            kx, ky, kw, kh = rect
            if kw < 1 or kh < 1:
                continue
            held = gdi32.CreateRectRgn(int(kx), int(ky), int(kx + kw), int(ky + kh))
            gdi32.CombineRgn(cut, cut, held, 4)  # RGN_DIFF: clicks stay on the overlay
            gdi32.DeleteObject(held)
        gdi32.CombineRgn(full, full, cut, 4)  # RGN_DIFF
        gdi32.DeleteObject(cut)
        if not user32.SetWindowRgn(hwnd, full, True):
            return ActionResult(False, "Windows did not apply the overlay hole.", reason="region_failed")
        return ActionResult(True, "Overlay hole is click-through.", reason="region_set")
    except Exception as exc:
        return ActionResult(False, f"I could not cut the overlay hole. {exc}", reason="region_error")


def design_size() -> tuple[int, int]:
    return OVERLAY_SIZE if OVERLAY_SIZE else (OUTPUT_W, OUTPUT_H)
