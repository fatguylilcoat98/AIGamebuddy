"""The pixel check must reject a bare window and accept the real frame."""
from PIL import Image, ImageDraw

from backend.frame_proof import prove_snes_screen
from backend.overlay_view import compose_overlay


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


def test_chrome_requires_the_button_and_the_open_menu():
    image = compose_overlay(
        "snes", (1920, 1080), expression="idle", character="male", resting="left", game_running=True,
    )
    missing = prove_snes_screen(image, menu_open=True, expect_chrome=True)
    assert any("hamburger" in item for item in missing)
    draw = ImageDraw.Draw(image)
    # Button and panel in the same place the live overlay uses at 1920x1080.
    draw.rounded_rectangle((27, 18, 192, 117), 12, fill=(26, 16, 40), outline=(126, 231, 255), width=3)
    draw.line((60, 48, 160, 48), fill=(246, 241, 255), width=4)
    draw.line((60, 68, 160, 68), fill=(246, 241, 255), width=4)
    draw.line((60, 88, 160, 88), fill=(246, 241, 255), width=4)
    draw.rectangle((40, 150, 500, 280), fill=(20, 12, 28))
    draw.text((60, 170), "Buddy", fill=(126, 231, 255))
    problems = prove_snes_screen(image, menu_open=True, expect_chrome=True)
    assert problems == [], problems
