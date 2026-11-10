"""Approved overlay frames: system map and measured game windows."""
from pathlib import Path

from PIL import Image

from backend.frame_library import (
    ASPECT_RATIO_CUSTOM,
    FRAME_DIR,
    FRAME_FILES,
    SYSTEM_ALIASES,
    buddy_well_rect,
    clear_painted_head,
    enlarge_screen,
    frame_for_system,
    hologram_blue_pixels,
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
        grown = enlarge_screen(image, frame_id, measured)
        stored = metadata["frames"][frame_id]["screen"]
        assert stored == grown
        assert stored["width"] > measured["width"]
        assert stored["width"] > 400 and stored["height"] > 300
        punched = punch_screen(image, stored, frame_id=frame_id)
        center = punched.getpixel((stored["x"] + stored["width"] // 2, stored["y"] + stored["height"] // 2))
        assert center[3] == 0
        import numpy as np
        x, y, w, h = stored["x"], stored["y"], stored["width"], stored["height"]
        hole = np.array(punched.crop((x, y, x + w, y + h)))
        alpha = hole[:, :, 3]
        inner = alpha[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)]
        assert int((inner > 16).sum()) == 0
        # The pad may cover the bottom edge. Scenery above that stays a thin overhang.
        above = alpha[:int(h * 0.82), :]
        opaque = int((above > 200).sum())
        assert 0 < opaque < int(above.size * 0.22)
        buddy = metadata["frames"][frame_id]["buddy"]
        menu = metadata["frames"][frame_id]["menu"]
        # The menu is a panel above the portrait, in Buddy's column, not under it.
        assert menu["x"] >= buddy["x"] - 2
        assert menu["x"] + menu["width"] <= buddy["x"] + buddy["width"] + 4
        assert menu["y"] + menu["height"] <= buddy["y"] + 8
        assert menu["height"] >= 160
        below = buddy["y"] + buddy["height"] + 20
        if below + 12 < image.size[1]:
            import numpy as np
            strip = np.asarray(image.convert("RGB"))[below:below + 12, buddy["x"]:buddy["x"] + buddy["width"]]
            assert float(strip.std()) > 8 or float(strip.mean()) > 28, frame_id


def test_viewports_and_retroarch_flags():
    metadata = load_metadata()
    for frame_id, record in metadata["frames"].items():
        view_720 = record["viewports"]["720p"]
        view_1080 = record["viewports"]["1080p"]
        assert view_720 == scale_rect(record["screen"], (1280, 720))
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


def test_painted_head_clears_without_eating_the_corner():
    for frame_id, filename in FRAME_FILES.items():
        image = Image.open(FRAME_DIR / filename)
        cleared = clear_painted_head(image, frame_id)
        well = buddy_well_rect(image, frame_id)
        assert hologram_blue_pixels(cleared, well) == 0
        assert cleared.convert("RGB").getpixel((2, 2)) == image.convert("RGB").getpixel((2, 2))
