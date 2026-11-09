"""Approved overlay frames: system map and measured game windows."""
from pathlib import Path

from PIL import Image

from backend.frame_library import (
    ASPECT_RATIO_CUSTOM,
    FRAME_DIR,
    FRAME_FILES,
    SYSTEM_ALIASES,
    frame_for_system,
    load_metadata,
    measure_screen,
    punch_screen,
    scale_rect,
    write_runtime_retroarch_cfg,
)


def test_system_map_covers_the_three_families_and_stays_open():
    assert frame_for_system("genesis") == "genesis"
    assert frame_for_system("megadrive") == "genesis"
    assert frame_for_system("mega drive") == "genesis"
    assert frame_for_system("nes") == "nes"
    assert frame_for_system("famicom") == "nes"
    assert frame_for_system("snes") == "snes"
    assert frame_for_system("sfc") == "snes"
    assert frame_for_system("super famicom") == "snes"
    assert frame_for_system("n64") is None
    assert frame_for_system("atari") is None
    # A new console is a new alias, not a new function.
    SYSTEM_ALIASES["atari"] = "atari"
    try:
        assert frame_for_system("atari") == "atari"
    finally:
        del SYSTEM_ALIASES["atari"]


def test_measured_screen_matches_metadata_and_keeps_the_controller():
    metadata = load_metadata()
    assert metadata["product_name"] == "Buddy Overlay"
    assert metadata["tagline"] == "Retro games, real attitude"
    for frame_id, filename in FRAME_FILES.items():
        image = Image.open(FRAME_DIR / filename)
        measured = measure_screen(image)
        stored = metadata["frames"][frame_id]["screen"]
        assert measured == stored
        assert stored["width"] > 400 and stored["height"] > 300
        punched = punch_screen(image, stored)
        center = punched.getpixel((stored["x"] + stored["width"] // 2, stored["y"] + stored["height"] // 2))
        assert center[3] == 0
        # The footer controller overlaps the window, so some pixels there stay opaque.
        overlap = punched.getpixel((stored["x"] + stored["width"] // 2, stored["y"] + stored["height"] - 6))
        assert overlap[3] == 255
        assert max(overlap[:3]) > 18
        buddy = metadata["frames"][frame_id]["buddy"]
        menu = metadata["frames"][frame_id]["menu"]
        assert buddy["y"] + buddy["height"] <= menu["y"] + 8
        assert menu["x"] > stored["x"]


def test_viewports_and_retroarch_flags():
    metadata = load_metadata()
    for frame_id, record in metadata["frames"].items():
        view_720 = record["viewports"]["720p"]
        view_1080 = record["viewports"]["1080p"]
        assert view_720 == record["screen"]
        scaled = scale_rect(record["screen"], (1920, 1080))
        assert view_1080 == scaled
        cfg = (FRAME_DIR / "retroarch" / f"{frame_id}-1080p.cfg").read_text(encoding="utf-8")
        assert 'video_scale_integer = "false"' in cfg
        assert f'aspect_ratio_index = "{ASPECT_RATIO_CUSTOM}"' in cfg
        assert f'custom_viewport_width = "{view_1080["width"]}"' in cfg
        overlay = (FRAME_DIR / "overlays" / f"{frame_id}.cfg").read_text(encoding="utf-8")
        assert "overlay0_full_screen = true" in overlay
        assert Path(record["file"]).stem + ".png" in overlay


def test_runtime_cfg_is_absolute_and_matches_the_window(tmp_path):
    size = (1400, 900)
    path = write_runtime_retroarch_cfg("nes", size, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "../overlays" not in text
    viewport = scale_rect(load_metadata()["frames"]["nes"]["screen"], size)
    assert f'custom_viewport_width = "{viewport["width"]}"' in text
    assert f'custom_viewport_height = "{viewport["height"]}"' in text
    assert 'video_fullscreen = "false"' in text
    assert 'video_windowed_fullscreen = "true"' in text
    assert 'video_window_width = "1400"' in text
    overlay_line = next(line for line in text.splitlines() if line.startswith("input_overlay = "))
    overlay_path = Path(overlay_line.split("=", 1)[1].strip().strip('"'))
    assert overlay_path.is_absolute()
    overlay_text = overlay_path.read_text(encoding="utf-8")
    png_line = next(line for line in overlay_text.splitlines() if line.startswith("overlay0_overlay = "))
    png_path = Path(png_line.split("=", 1)[1].strip().strip('"'))
    assert png_path.is_absolute()
    assert png_path.exists()
