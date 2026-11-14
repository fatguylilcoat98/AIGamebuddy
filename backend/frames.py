"""Original era-style overlay frames.

The layout matches Chris's cabinet references: title bar, central game opening,
hamburger at the top right, Buddy box at the bottom right, generic controller.
Nothing here is a console logo, a game character, or a photograph.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from .layout_spec import BUDDY_BOX, BUDDY_SCREEN, HOLE, MENU_BUTTON, OUTPUT_H, OUTPUT_W

FONT = ImageFont.load_default()


@dataclass
class FrameArt:
    image: Image.Image
    labels: list[str] = field(default_factory=list)
    theme: str = ""


def _low(rect: tuple[int, int, int, int], block: int) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    return x // block, y // block, w // block, h // block


class Board:
    def __init__(self, block: int, background: tuple[int, int, int, int]):
        self.block = block
        self.width = OUTPUT_W // block
        self.height = OUTPUT_H // block
        self.image = Image.new("RGBA", (self.width, self.height), background)
        self.draw = ImageDraw.Draw(self.image)
        self.labels: list[str] = []

    def rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int, int]) -> None:
        if w <= 0 or h <= 0:
            return
        self.draw.rectangle((x, y, x + w - 1, y + h - 1), fill=color)

    def ellipse(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int, int]) -> None:
        self.draw.ellipse((x, y, x + w - 1, y + h - 1), fill=color)

    def text(self, x: int, y: int, value: str, color: tuple[int, int, int, int], scale: int = 2) -> None:
        self.labels.append(value)
        scratch = Image.new("RGBA", (len(value) * 8 + 8, 18), (0, 0, 0, 0))
        ImageDraw.Draw(scratch).text((0, 0), value, fill=color, font=FONT)
        box = scratch.getbbox()
        if not box:
            return
        stamp = scratch.crop(box)
        if scale != 1:
            stamp = stamp.resize((stamp.width * scale, stamp.height * scale), Image.Resampling.NEAREST)
        self.image.alpha_composite(stamp, (x, y))

    def finish(self) -> Image.Image:
        full = self.image.resize((OUTPUT_W, OUTPUT_H), Image.Resampling.NEAREST)
        punched = Image.new("RGBA", (HOLE[2], HOLE[3]), (0, 0, 0, 0))
        full.paste(punched, (HOLE[0], HOLE[1]))
        return full


def _hamburger(board: Board, color: tuple[int, int, int, int], plate: tuple[int, int, int, int]) -> None:
    x, y, w, h = _low(MENU_BUTTON, board.block)
    board.rect(x, y, w, h, plate)
    board.draw.rectangle((x, y, x + w - 1, y + h - 1), outline=color)
    bar_h = max(2, h // 6)
    gap = max(2, (h - bar_h * 3) // 4)
    for row in range(3):
        yy = y + gap + row * (bar_h + gap)
        board.rect(x + 3, yy, w - 6, bar_h, color)


def _buddy_box(board: Board, rim: tuple[int, int, int, int], inner: tuple[int, int, int, int],
               plate: tuple[int, int, int, int]) -> None:
    x, y, w, h = _low(BUDDY_BOX, board.block)
    board.rect(x, y, w, h, rim)
    board.rect(x + 2, y + 2, w - 4, h - 4, plate)
    sx, sy, sw, sh = _low(BUDDY_SCREEN, board.block)
    board.rect(sx, sy, sw, sh, inner)
    board.text(x + 4, y + 2, "BUDDY", (230, 255, 255, 255), scale=1)


def _banner(board: Board, text: str, color: tuple[int, int, int, int]) -> None:
    scratch = Image.new("RGBA", (len(text) * 8 + 8, 18), (0, 0, 0, 0))
    ImageDraw.Draw(scratch).text((0, 0), text, fill=color, font=FONT)
    box = scratch.getbbox()
    width = (box[2] - box[0]) if box else 80
    scale = 2 if width * 2 < board.width * 0.46 else 1
    drawn = width * scale
    board.text((board.width - drawn) // 2, 4, text, color, scale=scale)


def _badge(board: Board, text: str, fill: tuple[int, int, int, int], ink: tuple[int, int, int, int]) -> None:
    width = len(text) * 6 + 16
    x = (board.width - width) // 2
    y = board.height - 16
    board.rect(x, y, width, 14, fill)
    board.text(x + 6, y + 2, text, ink, scale=1)


def _dpad(board: Board, x: int, y: int, color: tuple[int, int, int, int]) -> None:
    board.rect(x + 6, y, 8, 22, color)
    board.rect(x, y + 7, 22, 8, color)


def _pad(board: Board, kind: str, x: int, y: int) -> None:
    if kind == "nes":
        board.draw.rounded_rectangle((x, y, x + 58, y + 18), radius=4, fill=(214, 188, 150, 255))
        board.rect(x + 6, y + 4, 4, 10, (30, 26, 24, 255))
        board.rect(x + 3, y + 7, 10, 4, (30, 26, 24, 255))
        board.ellipse(x + 34, y + 4, 8, 8, (190, 48, 42, 255))
        board.ellipse(x + 46, y + 4, 8, 8, (190, 48, 42, 255))
    elif kind == "genesis":
        board.draw.rounded_rectangle((x, y, x + 78, y + 20), radius=10, fill=(220, 252, 255, 255))
        board.rect(x + 8, y + 4, 4, 12, (20, 40, 70, 255))
        board.rect(x + 4, y + 8, 12, 4, (20, 40, 70, 255))
        for index, color in enumerate(((60, 220, 255, 255), (255, 80, 160, 255), (255, 230, 80, 255))):
            board.ellipse(x + 28 + index * 16, y + 4, 10, 10, color)
    else:
        board.draw.rounded_rectangle((x, y, x + 86, y + 20), radius=8, fill=(236, 220, 255, 255))
        board.rect(x + 8, y + 4, 4, 12, (70, 40, 110, 255))
        board.rect(x + 4, y + 8, 12, 4, (70, 40, 110, 255))
        board.ellipse(x + 40, y + 3, 8, 8, (255, 196, 80, 255))
        board.ellipse(x + 52, y + 6, 8, 8, (80, 210, 190, 255))
        board.ellipse(x + 46, y + 11, 8, 8, (255, 110, 170, 255))
        board.ellipse(x + 64, y + 8, 8, 8, (90, 80, 180, 255))


def _bricks(board: Board, x: int, y: int, w: int, h: int, brick: tuple[int, int, int, int],
            mortar: tuple[int, int, int, int]) -> None:
    board.rect(x, y, w, h, mortar)
    row_h = 6
    for row, yy in enumerate(range(y, y + h, row_h)):
        shift = 8 if row % 2 else 0
        for xx in range(x - 8 + shift, x + w, 16):
            board.rect(max(x, xx), yy, 14, row_h - 1, brick)


def render_nes(banner: str) -> FrameArt:
    dark = (18, 10, 12, 255)
    brick = (186, 78, 42, 255)
    brick_dark = (120, 46, 28, 255)
    mortar = (48, 24, 22, 255)
    stone = (86, 90, 98, 255)
    gold = (232, 186, 72, 255)
    board = Board(6, dark)
    _bricks(board, 0, 0, board.width, 24, brick, mortar)
    _bricks(board, 0, 24, 48, board.height - 24, brick, mortar)
    _bricks(board, 248, 24, board.width - 248, 74, brick_dark, mortar)
    _bricks(board, 248, 174, board.width - 248, board.height - 174, brick, mortar)
    board.rect(0, 156, 320, 24, stone)
    # Torches and a cave star. No people, no creatures copied from a game.
    for tx in (8, 30):
        board.rect(tx, 70, 3, 16, (90, 60, 40, 255))
        board.ellipse(tx - 3, 58, 9, 12, (255, 170, 48, 255))
    board.ellipse(280, 40, 10, 10, gold)
    board.rect(18, 120, 16, 12, gold)
    board.rect(20, 124, 12, 4, (120, 72, 24, 255))
    for col in range(6, 40, 8):
        board.ellipse(col, 166, 4, 4, gold)
    hole = _low(HOLE, 6)
    board.draw.rectangle((hole[0] - 2, hole[1] - 2, hole[0] + hole[2] + 1, hole[1] + hole[3] + 1),
                         outline=gold, width=2)
    _pad(board, "nes", 6, 160)
    _buddy_box(board, gold, (6, 8, 16, 255), (42, 22, 18, 255))
    _hamburger(board, (255, 244, 220, 255), (48, 18, 16, 255))
    _banner(board, banner, (255, 236, 210, 255))
    _badge(board, "8-BIT", (42, 22, 18, 255), gold)
    return FrameArt(board.finish(), board.labels, "nes")


def render_snes(banner: str) -> FrameArt:
    sky = (74, 46, 140, 255)
    board = Board(4, sky)
    for y, color in enumerate(((92, 64, 168, 255), (120, 90, 190, 255), (168, 130, 210, 255), (210, 170, 230, 255))):
        board.rect(0, y * 8, board.width, 8, color)
    # Clouds and floating islands. Flowers are pink blossoms, not item mushrooms.
    for cx, cy in ((20, 18), (70, 10), (400, 16), (440, 28)):
        board.ellipse(cx, cy, 28, 12, (255, 236, 250, 255))
    def island(x: int, y: int, w: int) -> None:
        board.draw.polygon([(x, y + 16), (x + 10, y), (x + w - 10, y), (x + w, y + 16),
                           (x + w - 16, y + 34), (x + 16, y + 34)], fill=(92, 64, 48, 255))
        board.rect(x + 8, y - 6, w - 16, 10, (72, 170, 90, 255))
        board.ellipse(x + 16, y - 16, 10, 8, (255, 150, 190, 255))
        board.ellipse(x + w - 30, y - 14, 8, 8, (255, 190, 210, 255))
    island(8, 70, 70)
    island(390, 78, 80)
    board.rect(24, 100, 4, 40, (120, 210, 240, 255))
    board.rect(430, 110, 4, 36, (120, 210, 240, 255))
    # A plain castle mass, not a character.
    board.rect(18, 48, 28, 22, (230, 226, 245, 255))
    board.rect(14, 42, 8, 12, (230, 226, 245, 255))
    board.rect(42, 42, 8, 12, (230, 226, 245, 255))
    board.rect(28, 58, 6, 12, (90, 70, 120, 255))
    hole = _low(HOLE, 4)
    board.draw.rectangle((hole[0] - 3, hole[1] - 3, hole[0] + hole[2] + 2, hole[1] + hole[3] + 2),
                         outline=(255, 210, 120, 255), width=3)
    board.rect(0, 246, board.width, 24, (48, 28, 84, 255))
    _pad(board, "snes", 12, 246)
    _buddy_box(board, (255, 196, 110, 255), (18, 8, 36, 255), (48, 24, 84, 255))
    _hamburger(board, (255, 244, 255, 255), (36, 16, 72, 255))
    _banner(board, banner, (255, 244, 255, 255))
    _badge(board, "SUPER 16-BIT", (48, 24, 84, 255), (255, 214, 130, 255))
    return FrameArt(board.finish(), board.labels, "snes")


def render_genesis(banner: str) -> FrameArt:
    board = Board(4, (8, 12, 32, 255))
    for y in range(0, 80):
        shade = 10 + y // 2
        board.rect(0, y, board.width, 1, (shade, shade + 8, 48 + y // 3, 255))
    # Stars, a moon, and a skyline. No hedgehog, no ring, no company mark.
    for sx, sy in ((12, 8), (40, 18), (90, 10), (300, 14), (360, 8), (20, 30)):
        board.rect(sx, sy, 2, 2, (240, 240, 255, 255))
    board.ellipse(300, 36, 22, 22, (230, 236, 255, 255))
    board.ellipse(306, 34, 16, 16, (8, 16, 40, 255))
    for index, height in enumerate((28, 40, 22, 48, 18, 34)):
        board.rect(390 + index * 12, 120 - height, 10, height, (18, 28, 58, 255))
        board.rect(392 + index * 12, 124 - height, 2, 2, (255, 220, 120, 255))
    # Left cliff and a plain waterfall.
    board.draw.polygon([(0, 90), (40, 70), (70, 100), (60, 200), (0, 200)], fill=(18, 90, 80, 255))
    board.rect(28, 100, 6, 70, (40, 140, 200, 255))
    board.ellipse(8, 78, 16, 10, (30, 140, 70, 255))
    board.ellipse(20, 86, 14, 9, (30, 150, 80, 255))
    # Speed stripes sit beside the title, not through the letters.
    for stripe in range(3):
        board.rect(8, 8 + stripe * 5, 70, 2, (60, 220, 255, 255) if stripe % 2 == 0 else (255, 60, 140, 255))
        board.rect(360, 8 + stripe * 5, 70, 2, (255, 60, 140, 255) if stripe % 2 == 0 else (60, 220, 255, 255))
    hole = _low(HOLE, 4)
    board.draw.rectangle((hole[0] - 3, hole[1] - 3, hole[0] + hole[2] + 2, hole[1] + hole[3] + 2),
                         outline=(60, 220, 255, 255), width=3)
    board.rect(0, 246, board.width, 24, (12, 20, 48, 255))
    _pad(board, "genesis", 8, 242)
    _buddy_box(board, (60, 220, 255, 255), (4, 10, 24, 255), (16, 28, 64, 255))
    _hamburger(board, (230, 255, 255, 255), (8, 16, 40, 255))
    _banner(board, banner, (240, 250, 255, 255))
    _badge(board, "16-BIT", (16, 28, 64, 255), (60, 220, 255, 255))
    return FrameArt(board.finish(), board.labels, "genesis")


RENDERERS = {"nes": render_nes, "snes": render_snes, "genesis": render_genesis}


def render_frame(theme: str, banner: str = "GAME WINGMAN") -> FrameArt:
    if theme not in RENDERERS:
        raise ValueError(f"Unknown overlay theme: {theme}")
    safe = " ".join((banner or "GAME WINGMAN").upper().split())[:22] or "GAME WINGMAN"
    return RENDERERS[theme](safe)


def composite_with_head(frame: FrameArt, head: Image.Image) -> Image.Image:
    image = frame.image.copy()
    x, y, w, h = BUDDY_SCREEN
    fitted = head.resize((w, h), Image.Resampling.LANCZOS)
    image.alpha_composite(fitted, (x, y))
    return image
