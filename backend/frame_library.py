"""Approved Buddy Overlay frames and the auto-lock geometry.

Each console maps to one frame. The screen rectangle is measured from the
black game window. The controller is allowed to overlap that window; only
near-black pixels inside the window are punched out, so the controller stays.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
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
    "genesis": {
        "buddy": {"x": 1024, "y": 332, "width": 240, "height": 276},
        "menu": {"x": 1004, "y": 616, "width": 254, "height": 94},
    },
    "nes": {
        "buddy": {"x": 1020, "y": 340, "width": 240, "height": 258},
        "menu": {"x": 1004, "y": 606, "width": 260, "height": 102},
    },
    "snes": {
        "buddy": {"x": 1016, "y": 328, "width": 248, "height": 262},
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


def scale_rect(rect: dict[str, int], target: tuple[int, int]) -> dict[str, int]:
    sx = target[0] / DESIGN["width"]
    sy = target[1] / DESIGN["height"]
    return {
        "x": int(round(rect["x"] * sx)),
        "y": int(round(rect["y"] * sy)),
        "width": int(round(rect["width"] * sx)),
        "height": int(round(rect["height"] * sy)),
    }


def punch_screen(image: Image.Image, screen: dict[str, int], threshold: int = 18) -> Image.Image:
    """Cut the game window to alpha. Non-black pixels, including the controller, stay."""
    rgba = np.array(image.convert("RGBA"))
    x, y, w, h = screen["x"], screen["y"], screen["width"], screen["height"]
    region = rgba[y:y + h, x:x + w]
    black = region[:, :, :3].max(axis=2) <= threshold
    region[:, :, 3] = np.where(black, 0, 255)
    rgba[y:y + h, x:x + w] = region
    return Image.fromarray(rgba, "RGBA")


def build_metadata() -> dict:
    frames = {}
    for frame_id, filename in FRAME_FILES.items():
        path = FRAME_DIR / filename
        screen = measure_screen(Image.open(path))
        placement = PLACEMENTS[frame_id]
        viewports = {name: scale_rect(screen, size) for name, size in OUTPUTS.items()}
        frames[frame_id] = {
            "file": filename,
            "systems": [alias for alias, target in SYSTEM_ALIASES.items() if target == frame_id],
            "screen": screen,
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
        source = Image.open(FRAME_DIR / record["file"])
        png_name = Path(record["file"]).stem + ".png"
        png_path = OVERLAY_DIR / png_name
        punch_screen(source, record["screen"]).save(png_path)
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
    for path in write_outputs():
        print(path)
