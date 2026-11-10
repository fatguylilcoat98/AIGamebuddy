"""The pixel check must reject a bare window and accept the real frame."""
from PIL import Image, ImageDraw

from backend.frame_proof import prove_snes_screen
from backend.overlay_view import compose_overlay


def test_seal_keeps_only_the_game_rectangle_clear():
    from backend.overlay_view import seal_opening
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    sealed = seal_opening(image, {"x": 10, "y": 10, "width": 10, "height": 10})
    assert sealed.getpixel((5, 5)) == (0, 0, 0, 255)
    assert sealed.getpixel((15, 15))[3] == 0


def test_a_blank_screen_is_not_the_snes_frame():
    blank = Image.new("RGB", (1920, 1080), (7, 8, 13))
    problems = prove_snes_screen(blank, menu_open=False, expect_chrome=False)
    assert problems
    assert any("frame" in item.lower() or "art" in item.lower() or "scenery" in item.lower() for item in problems)


def test_the_composed_frame_shows_the_painting_and_buddy():
    image = compose_overlay(
        "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )
    problems = prove_snes_screen(image, menu_open=False, expect_chrome=False)
    assert problems == [], problems


def _game_at_1080() -> tuple[int, int, int, int]:
    from backend.frame_library import DESIGN, frame_record
    screen = frame_record("snes")["screen"]
    sx = 1920 / DESIGN["width"]
    sy = 1080 / DESIGN["height"]
    return (
        int(round(screen["x"] * sx)),
        int(round(screen["y"] * sy)),
        int(round(screen["width"] * sx)),
        int(round(screen["height"] * sy)),
    )


def test_wallpaper_in_the_opening_ring_is_rejected():
    image = compose_overlay(
        "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )
    x, y, w, _h = _game_at_1080()
    draw = ImageDraw.Draw(image)
    draw.rectangle((x + w // 5, y - 14, x + (4 * w) // 5, y - 4), fill=(170, 200, 230))
    problems = prove_snes_screen(image, menu_open=False, expect_chrome=False)
    assert any("desktop" in item for item in problems), problems


def test_a_white_menu_bar_on_the_game_is_rejected():
    image = compose_overlay(
        "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )
    x, y, w, _h = _game_at_1080()
    draw = ImageDraw.Draw(image)
    draw.rectangle((x + w // 2, y, x + w - 8, y + 36), fill=(240, 240, 240))
    problems = prove_snes_screen(image, menu_open=False, expect_chrome=False)
    assert any("menu bar" in item for item in problems), problems


def test_a_small_center_picture_does_not_count_as_filling_the_opening():
    image = compose_overlay(
        "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )
    x, y, w, h = _game_at_1080()
    draw = ImageDraw.Draw(image)
    draw.rectangle((x + w // 3, y + h // 3, x + (2 * w) // 3, y + (2 * h) // 3), fill=(0, 0, 255))
    problems = prove_snes_screen(image, menu_open=False, expect_chrome=False, expect_game=True)
    assert any("fills" in item for item in problems), problems


def test_a_four_by_three_picture_fills_the_opening_height():
    image = compose_overlay(
        "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )
    x, y, w, h = _game_at_1080()
    picture_w = int(round(h * 4 / 3))
    left = x + (w - picture_w) // 2
    draw = ImageDraw.Draw(image)
    draw.rectangle((left, y, left + picture_w, y + h), fill=(0, 0, 255))
    problems = prove_snes_screen(image, menu_open=False, expect_chrome=False, expect_game=True)
    assert problems == [], problems


def _button_at_1080() -> tuple[int, int, int, int]:
    from backend.frame_library import DESIGN
    box = {"x": 36, "y": 24, "width": 220, "height": 132}
    sx = 1920 / DESIGN["width"]
    sy = 1080 / DESIGN["height"]
    return (
        int(round(box["x"] * sx)),
        int(round(box["y"] * sy)),
        int(round(box["width"] * sx)),
        int(round(box["height"] * sy)),
    )


def test_the_painted_menu_button_is_part_of_the_frame():
    image = compose_overlay(
        "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )
    problems = prove_snes_screen(image, menu_open=False, expect_chrome=True)
    assert not any("hamburger" in item for item in problems), problems
    x, y, w, h = _button_at_1080()
    draw = ImageDraw.Draw(image)
    draw.rectangle((x, y, x + w, y + h), fill=(4, 4, 6))
    covered = prove_snes_screen(image, menu_open=False, expect_chrome=True)
    assert any("flat dark" in item for item in covered), covered


def test_chrome_requires_the_open_menu():
    image = compose_overlay(
        "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )
    missing = prove_snes_screen(image, menu_open=True, expect_chrome=True)
    assert any("menu panel" in item for item in missing)
    x, y, w, h = _button_at_1080()
    draw = ImageDraw.Draw(image)
    draw.rectangle((x + 8, y + h + 28, x + 8 + 420, y + h + 108), fill=(20, 12, 28))
    draw.text((x + 24, y + h + 48), "Buddy", fill=(126, 231, 255))
    problems = prove_snes_screen(image, menu_open=True, expect_chrome=True)
    assert problems == [], problems
