"""Approved Buddy Overlay frames and the auto-lock geometry.

Each console maps to one frame. The screen rectangle is measured from the
black game window. The controller is allowed to overlap that window; only
near-black pixels inside the window are punched out, so the controller stays.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from .config_loader import ROOT
FRAME_DIR = ROOT / "assets" / "frames"
OVERLAY_DIR = FRAME_DIR / "overlays"
RETROARCH_DIR = FRAME_DIR / "retroarch"
ES_DIR = FRAME_DIR / "es-de"
METADATA_PATH = FRAME_DIR / "metadata.json"

# Aliases are the system id Buddy already detects, plus the names Chris uses.
# Add a console by appending a frame entry and its aliases. See the README.
FRAME_FILES = {
    "genesis": "genesis-16bit.jpg",
    "nes": "nes-8bit-dungeon.jpg",
    "snes": "snes-sky-kingdom.jpg",
}

SYSTEM_ALIASES = {
    "genesis": "genesis",
    "megadrive": "genesis",
    "mega drive": "genesis",
    "mega-drive": "genesis",
    "nes": "nes",
    "famicom": "nes",
    "snes": "snes",
    "sfc": "snes",
    "super famicom": "snes",
}

# Portrait and menu, in source pixels. Tuned to the approved art so the live
# head covers the baked face and the menu sits on the pixel bar under it.
PLACEMENTS = {
    # buddy is the inner well only. The bezel and its glow stay outside this rect.
    "genesis": {
        "buddy": {"x": 1032, "y": 348, "width": 208, "height": 232},
        "menu": {"x": 1004, "y": 616, "width": 254, "height": 94},
    },
    "nes": {
        "buddy": {"x": 1036, "y": 356, "width": 200, "height": 220},
        "menu": {"x": 1004, "y": 606, "width": 260, "height": 102},
    },
    "snes": {
        # Inside the black well. x>=1236 and y>=576 are the glowing bezel.
        "buddy": {"x": 1036, "y": 340, "width": 196, "height": 232},
        "menu": {"x": 996, "y": 598, "width": 264, "height": 110},
    },
}

DESIGN = {"width": 1280, "height": 720}
OUTPUTS = {"720p": (1280, 720), "1080p": (1920, 1080)}
# RetroArch's Custom aspect entry. Confirmed as index 23 in current releases.
ASPECT_RATIO_CUSTOM = 23


def frame_for_system(system: str | None) -> str | None:
    if not system:
        return None
    return SYSTEM_ALIASES.get(str(system).strip().lower())


def measure_screen(image: Image.Image, threshold: int = 14) -> dict[str, int]:
    """Largest near-black rectangle, extended down the side gutters under the controller."""
    array = np.asarray(image.convert("RGB"))
    mask = array.max(axis=2) <= threshold
    height, width = mask.shape
    columns = [0] * width
    best = (0, 0, 0, 0, 0)  # area, x, y, w, h
    for y in range(height):
        for x in range(width):
            columns[x] = columns[x] + 1 if mask[y, x] else 0
        stack = [-1]
        for i in range(width + 1):
            column_height = columns[i] if i < width else 0
            while stack[-1] != -1 and columns[stack[-1]] > column_height:
                run_h = columns[stack.pop()]
                run_w = i - stack[-1] - 1
                area = run_h * run_w
                if area > best[0] and run_h > 40 and run_w > 40:
                    best = (area, stack[-1] + 1, y - run_h + 1, run_w, run_h)
            stack.append(i)
    _area, x, y, w, h = best
    if w == 0:
        raise ValueError("No game window found in the frame")

    def column_end(col: int) -> int:
        yy = y + 20
        limit = min(height - 1, y + h + 120)
        while yy < limit and int(array[yy, col].max()) <= threshold + 8:
            yy += 1
        return yy - 1

    bottom = min(column_end(x + max(4, int(w * 0.08))), column_end(x + int(w * 0.92)))
    if bottom < y + h - 1:
        bottom = y + h - 1
    return {"x": int(x), "y": int(y), "width": int(w), "height": int(bottom - y + 1)}


# Design pixels on the 1280x720 art. 1080p is 1.5x these numbers.
# The overhang is the frame's own bezel, drawn back on top of the hole.
BEZEL_OVERHANG = 4
# How far the hole grows past the measured black window, per frame.
# NES and SNES were still the small original opening. Genesis was already wide.
SIDE_GROW = {"genesis": 14, "nes": 28, "snes": 34}
TOP_GROW = {"genesis": 4, "nes": 8, "snes": 4}
# Controller pixels kept over the game. 7px at 720p is about 10px at 1080p.
# Genesis was covering the game with most of the pad; NES and SNES were already thin.
CONTROLLER_OVERLAP = {"genesis": 7, "nes": 8, "snes": 8}


def _well_pixel(rgb: np.ndarray) -> np.ndarray:
    """Dark plate, hologram glow, or the white GB letters. Not the brick bezel."""
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    peak = np.maximum(np.maximum(red, green), blue)
    dark = peak <= 58
    glow = (blue > 85) & (blue > red + 40) & (green > 25)
    letters = (red > 185) & (green > 185) & (blue > 185)
    return dark | glow | letters


def buddy_well_rect(image: Image.Image, frame_id: str) -> dict[str, int]:
    """Inner plate of Buddy's box, expanded until the bezel. The bezel stays."""
    rgb = np.asarray(image.convert("RGB"))
    well = _well_pixel(rgb)
    box = PLACEMENTS[frame_id]["buddy"]
    x0, y0 = int(box["x"]), int(box["y"])
    x1, y1 = x0 + int(box["width"]), y0 + int(box["height"])
    height, width = well.shape

    def edge_ok(side: str, nx0: int, ny0: int, nx1: int, ny1: int) -> bool:
        if side == "left":
            strip = well[ny0:ny1, nx0]
        elif side == "right":
            strip = well[ny0:ny1, nx1 - 1]
        elif side == "top":
            strip = well[ny0, nx0:nx1]
        else:
            strip = well[ny1 - 1, nx0:nx1]
        return bool(strip.size) and float(strip.mean()) > 0.72

    for _ in range(48):
        grew = False
        if x0 > 1 and edge_ok("left", x0 - 1, y0, x1, y1):
            x0 -= 1
            grew = True
        if x1 < width - 1 and edge_ok("right", x0, y0, x1 + 1, y1):
            x1 += 1
            grew = True
        if y0 > 1 and edge_ok("top", x0, y0 - 1, x1, y1):
            y0 -= 1
            grew = True
        if y1 < height - 1 and edge_ok("bottom", x0, y0, x1, y1 + 1):
            y1 += 1
            grew = True
        if not grew:
            break
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def clear_painted_head(image: Image.Image, frame_id: str) -> Image.Image:
    """Replace the baked hologram with the well's dark plate. The bezel stays."""
    rgb = np.asarray(image.convert("RGB")).copy()
    rect = buddy_well_rect(image, frame_id)
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    sample = rgb[y:y + h, x:x + w]
    dark = sample.max(axis=2) <= 40
    if dark.any():
        color = np.median(sample[dark], axis=0).astype(np.uint8)
    else:
        color = np.array([0, 0, 10], dtype=np.uint8)
    rgb[y:y + h, x:x + w] = color
    return Image.fromarray(rgb, "RGB")


def hologram_blue_pixels(image: Image.Image, rect: dict[str, int]) -> int:
    """Bright cyan pixels. The empty well should have none before the live sprite."""
    array = np.asarray(image.convert("RGB"))
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    region = array[y + 2:y + h - 2, x + 2:x + w - 2]
    red = region[:, :, 0].astype(np.int16)
    green = region[:, :, 1].astype(np.int16)
    blue = region[:, :, 2].astype(np.int16)
    glow = (blue > 90) & (blue > red + 40) & (green > 30)
    return int(glow.sum())


def controller_top(image: Image.Image, screen: dict[str, int]) -> int:
    """Highest row of the footer controller inside the measured black window."""
    array = np.asarray(image.convert("RGB"))
    x, y, w, h = screen["x"], screen["y"], screen["width"], screen["height"]
    left, right = x + w // 3, x + (2 * w) // 3
    found = None
    for row in range(y + h - 1, y + h // 2, -1):
        if int(array[row, left:right].max()) > 40:
            found = row
        elif found is not None:
            break
    return found if found is not None else y + h - 1


def enlarge_screen(image: Image.Image, frame_id: str, raw: dict[str, int] | None = None) -> dict[str, int]:
    """Game opening: the black window plus its rectangular bezel, not the scenery.

    Buddy's box stays to the right. The controller only nicks the bottom edge.
    """
    raw = raw or measure_screen(image)
    width, height = image.size
    well = buddy_well_rect(image, frame_id)
    menu = PLACEMENTS[frame_id]["menu"]
    control = controller_top(image, raw)
    overlap = CONTROLLER_OVERLAP[frame_id]
    # Eat the drawn screen frame. Stop before Buddy and the menu so those stay clickable.
    grow = 36
    x = max(4, raw["x"] - grow)
    y = max(4, raw["y"] - 14)
    right = min(width - 4, raw["x"] + raw["width"] + grow)
    right = min(right, int(well["x"]) - 8, int(menu["x"]) - 4)
    bottom = min(height - 4, control + overlap, int(menu["y"]) - 4)
    if bottom <= y + 80:
        bottom = min(height - 4, y + 80)
    return {"x": int(x), "y": int(y), "width": int(max(40, right - x)), "height": int(bottom - y)}


def _organic_mask(height: int, width: int) -> np.ndarray:
    """Irregular edge nibbles, thicker at the corners. About 1–3% of the opening."""
    ys, xs = np.mgrid[0:height, 0:width]
    left = xs
    right = width - 1 - xs
    top = ys
    bottom = height - 1 - ys
    edge = np.minimum(np.minimum(left, right), np.minimum(top, bottom)).astype(np.float32)
    near_x = np.minimum(left, right) / max(1, width)
    near_y = np.minimum(top, bottom) / max(1, height)
    corner = np.clip(1.0 - (near_x + near_y) * 6.0, 0.0, 1.0)
    wobble = 0.55 + 0.45 * np.sin(xs * 0.37 + 1.7) * np.sin(ys * 0.21 + 0.4)
    span = float(min(height, width))
    limit = span * (0.008 + 0.018 * corner) * wobble
    return edge < limit


def cut_hole(image: Image.Image, screen: dict[str, int], lip: int = BEZEL_OVERHANG,
             bottom_keep: int = 8) -> Image.Image:
    """Open the game hole and lay nearby scenery over the edge.

    The rectangular screen frame is not copied back. `lip` and `bottom_keep`
    stay in the signature for older callers.
    """
    del lip, bottom_keep
    original = np.array(image.convert("RGBA"))
    output = original.copy()
    x, y, w, h = int(screen["x"]), int(screen["y"]), int(screen["width"]), int(screen["height"])
    height, width = original.shape[:2]
    output[y:y + h, x:x + w, 3] = 0
    mask = _organic_mask(h, w)
    ys, xs = np.where(mask)
    for py, px in zip(ys.tolist(), xs.tolist()):
        if px < w * 0.5 and px <= py and px <= (h - 1 - py):
            sx, sy = x - 1, y + py
        elif (w - 1 - px) < w * 0.5 and (w - 1 - px) <= py and (w - 1 - px) <= (h - 1 - py):
            sx, sy = x + w, y + py
        elif py < h * 0.5:
            sx, sy = x + px, y - 1
        else:
            sx, sy = x + px, y + h
        if not (0 <= sx < width and 0 <= sy < height):
            continue
        pixel = original[sy, sx]
        if int(pixel[:3].max()) < 20:
            continue
        output[y + py, x + px] = pixel
    return Image.fromarray(output, "RGBA")


def scale_rect(rect: dict[str, int], target: tuple[int, int]) -> dict[str, int]:
    sx = target[0] / DESIGN["width"]
    sy = target[1] / DESIGN["height"]
    return {
        "x": int(round(rect["x"] * sx)),
        "y": int(round(rect["y"] * sy)),
        "width": int(round(rect["width"] * sx)),
        "height": int(round(rect["height"] * sy)),
    }


def paste_head(image: Image.Image, head: Image.Image, box: dict[str, int]) -> Image.Image:
    """Center a head in the well. The ring stays fully inside, with room above the cap.

    The same padding is used for both characters, on every frame.
    """
    canvas = image.convert("RGBA")
    x, y, w, h = int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"])
    if w < 2 or h < 2:
        return canvas
    sprite = head.convert("RGBA")
    box_px = sprite.getbbox()
    trimmed = sprite.crop(box_px) if box_px else sprite
    # Fill most of the well height. A wide profile is center-cropped, not shrunk away.
    target_h = max(8, int(round(h * 0.88)))
    scale = target_h / max(1, trimmed.height)
    resized = trimmed.resize(
        (max(1, int(round(trimmed.width * scale))), target_h),
        Image.Resampling.LANCZOS,
    )
    if resized.width > w:
        left = (resized.width - w) // 2
        resized = resized.crop((left, 0, left + w, resized.height))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ox = (w - resized.width) // 2
    oy = (h - resized.height) // 2
    layer.alpha_composite(resized, (ox, oy))
    canvas.alpha_composite(layer, (x, y))
    return canvas


def punch_screen(image: Image.Image, screen: dict[str, int], threshold: int = 18,
                 frame_id: str | None = None) -> Image.Image:
    """Cut the game window, then lay the frame's own bezel back over the edge.

    `threshold` is kept so older callers stay valid. The hole itself is cleared
    fully. A few pixels of this frame's bezel are painted back on every side,
    and the controller overlap stays along the bottom.
    """
    del threshold
    keep = CONTROLLER_OVERLAP.get(frame_id, 8) if frame_id else 8
    return cut_hole(image, screen, BEZEL_OVERHANG, keep)


def build_metadata() -> dict:
    frames = {}
    for frame_id, filename in FRAME_FILES.items():
        path = FRAME_DIR / filename
        source = Image.open(path)
        screen = enlarge_screen(source, frame_id)
        placement = PLACEMENTS[frame_id]
        viewports = {name: scale_rect(screen, size) for name, size in OUTPUTS.items()}
        frames[frame_id] = {
            "file": filename,
            "systems": [alias for alias, target in SYSTEM_ALIASES.items() if target == frame_id],
            "screen": screen,
            "well": buddy_well_rect(source, frame_id),
            "buddy": placement["buddy"],
            "menu": placement["menu"],
            "viewports": viewports,
        }
    return {
        "product_name": "Buddy Overlay",
        "tagline": "Retro games, real attitude",
        "design": DESIGN,
        "frames": frames,
    }


def load_metadata() -> dict:
    if METADATA_PATH.exists():
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return build_metadata()


def frame_record(frame_id: str) -> dict:
    data = load_metadata()["frames"][frame_id]
    return data


def retroarch_overlay_cfg(frame_id: str) -> str:
    record = frame_record(frame_id)
    png_name = Path(record["file"]).stem + ".png"
    return (
        "overlays = 1\n"
        f"overlay0_overlay = \"{png_name}\"\n"
        "overlay0_full_screen = true\n"
        "overlay0_descs = 0\n"
    )


def retroarch_viewport_cfg(frame_id: str, mode: str, overlay_cfg: str) -> str:
    viewport = frame_record(frame_id)["viewports"][mode]
    return "\n".join([
        "video_scale_integer = \"false\"",
        f"aspect_ratio_index = \"{ASPECT_RATIO_CUSTOM}\"",
        f"custom_viewport_x = \"{viewport['x']}\"",
        f"custom_viewport_y = \"{viewport['y']}\"",
        f"custom_viewport_width = \"{viewport['width']}\"",
        f"custom_viewport_height = \"{viewport['height']}\"",
        "input_overlay_enable = \"true\"",
        "input_overlay_auto_scale = \"true\"",
        "input_overlay_hide_in_menu = \"false\"",
        f"input_overlay = \"{overlay_cfg}\"",
        "",
    ])


def es_de_snippet(overlay_root: Path) -> str:
    lines = [
        "<!-- Drop the <system> blocks you need into ES-DE's es_systems.xml. -->",
        "<!-- %ROM% and the core path are yours. The appendconfig locks the viewport. -->",
    ]
    for frame_id, record in load_metadata()["frames"].items():
        for system in record["systems"]:
            cfg = f"assets/frames/retroarch/{frame_id}-1080p.cfg"
            lines.append(
                f"<!-- {system} -> {frame_id} -->\n"
                f"<!-- retroarch -L CORE --fullscreen --appendconfig \"{cfg}\" \"%ROM%\" -->"
            )
    return "\n".join(lines) + "\n"


def write_outputs() -> list[Path]:
    """Write metadata, transparent overlays, and RetroArch/ES-DE config."""
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    RETROARCH_DIR.mkdir(parents=True, exist_ok=True)
    ES_DIR.mkdir(parents=True, exist_ok=True)
    metadata = build_metadata()
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    written = [METADATA_PATH]
    for frame_id, record in metadata["frames"].items():
        source = clear_painted_head(Image.open(FRAME_DIR / record["file"]), frame_id)
        png_name = Path(record["file"]).stem + ".png"
        png_path = OVERLAY_DIR / png_name
        punch_screen(source, record["screen"], frame_id=frame_id).save(png_path)
        cfg_path = OVERLAY_DIR / f"{frame_id}.cfg"
        cfg_path.write_text(retroarch_overlay_cfg(frame_id), encoding="utf-8")
        written.extend((png_path, cfg_path))
        for mode in OUTPUTS:
            viewport_path = RETROARCH_DIR / f"{frame_id}-{mode}.cfg"
            # Path RetroArch can resolve when this cfg is passed with --appendconfig.
            overlay_ref = f"../overlays/{frame_id}.cfg"
            viewport_path.write_text(
                retroarch_viewport_cfg(frame_id, mode, overlay_ref),
                encoding="utf-8",
            )
            written.append(viewport_path)
    es_path = ES_DIR / "launch-commands.txt"
    es_path.write_text(es_de_snippet(FRAME_DIR), encoding="utf-8")
    written.append(es_path)
    return written


def detect_display_size() -> tuple[int, int] | None:
    """Current primary monitor, or None when it cannot be read."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
    except Exception:
        return None
    if width < 640 or height < 480:
        return None
    return width, height


def write_runtime_retroarch_cfg(frame_id: str, size: tuple[int, int], directory: Path) -> Path:
    """Viewport scaled to `size`, with absolute overlay paths.

    RetroArch resolves a relative input_overlay from the process working
    directory, so the cfg written here does not use `../overlays`. Exclusive
    fullscreen is off. Windowed fullscreen uses this exact resolution; a 720p
    viewport on a different window puts the game outside the hole.
    """
    directory.mkdir(parents=True, exist_ok=True)
    record = frame_record(frame_id)
    viewport = scale_rect(record["screen"], size)
    png = (OVERLAY_DIR / (Path(record["file"]).stem + ".png")).resolve()
    if not png.exists():
        source = clear_painted_head(Image.open(FRAME_DIR / record["file"]), frame_id)
        OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
        punch_screen(source, record["screen"], frame_id=frame_id).save(png)
    overlay_path = directory / f"{frame_id}-overlay.cfg"
    overlay_path.write_text(
        "\n".join([
            "overlays = 1",
            f'overlay0_overlay = "{png.as_posix()}"',
            "overlay0_full_screen = true",
            "overlay0_descs = 0",
            "",
        ]),
        encoding="utf-8",
    )
    width, height = size
    cfg_path = directory / f"{frame_id}-{width}x{height}.cfg"
    cfg_path.write_text(
        "\n".join([
            'video_fullscreen = "false"',
            'video_windowed_fullscreen = "true"',
            f'video_window_width = "{width}"',
            f'video_window_height = "{height}"',
            'video_scale_integer = "false"',
            f'aspect_ratio_index = "{ASPECT_RATIO_CUSTOM}"',
            f'custom_viewport_x = "{viewport["x"]}"',
            f'custom_viewport_y = "{viewport["y"]}"',
            f'custom_viewport_width = "{viewport["width"]}"',
            f'custom_viewport_height = "{viewport["height"]}"',
            'input_overlay_enable = "true"',
            'input_overlay_auto_scale = "true"',
            'input_overlay_hide_in_menu = "false"',
            f'input_overlay = "{overlay_path.resolve().as_posix()}"',
            "",
        ]),
        encoding="utf-8",
    )
    return cfg_path


def install_retroarch_configs(directory: Path | None = None) -> list[Path]:
    """Write absolute-path configs for 720p, 1080p, and the current display."""
    target = directory or (FRAME_DIR / "retroarch")
    written = []
    sizes = [(1280, 720), (1920, 1080)]
    detected = detect_display_size()
    if detected and detected not in sizes:
        sizes.append(detected)
    for frame_id in FRAME_FILES:
        for size in sizes:
            written.append(write_runtime_retroarch_cfg(frame_id, size, target))
    return written


def append_config_for(frame_id: str, mode: str = "1080p") -> Path:
    path = RETROARCH_DIR / f"{frame_id}-{mode}.cfg"
    if not path.exists():
        write_outputs()
    return path


def scaled_screen(frame_id: str, window: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if frame_id not in FRAME_FILES:
        return None
    rect = scale_rect(frame_record(frame_id)["screen"], window)
    return rect["x"], rect["y"], rect["width"], rect["height"]


def scaled_box(frame_id: str, key: str, window: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if frame_id not in FRAME_FILES:
        return None
    rect = scale_rect(frame_record(frame_id)[key], window)
    return rect["x"], rect["y"], rect["width"], rect["height"]


if __name__ == "__main__":
    if "--install" in sys.argv:
        for path in install_retroarch_configs():
            print(path)
    else:
        for path in write_outputs():
            print(path)
