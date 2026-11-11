"""A 256x224 Super NES test pattern.

The picture is 4:3 with a different color on the left and the right, a pale
middle, and a bright top and bottom. It is not a flat 16:9 blue field. The
Windows run uses it so we can see the picture reach the edges of the opening.
It is public domain and is not shipped in the installer.
"""
from __future__ import annotations


def _tilemap() -> bytes:
    """32 by 28 words. Border palettes differ. The middle is another palette."""
    words = []
    for row in range(28):
        for col in range(32):
            if row == 0:
                palette = 1
            elif row == 27:
                palette = 2
            elif col == 0:
                palette = 3
            elif col == 31:
                palette = 4
            else:
                palette = 5
            words.append((palette << 10) & 0xFFFF)
    # Pad the rest of a 32x32 map so the PPU has a full screen base.
    words.extend([0] * (32 * 4))
    out = bytearray()
    for word in words:
        out.append(word & 0xFF)
        out.append((word >> 8) & 0xFF)
    return bytes(out)


def _cgram() -> bytes:
    """Color 1 of palettes 1-5 is the pixel the solid tile shows."""
    colors = {
        1: 0x001F,  # red
        2: 0x03E0,  # green
        3: 0x7C00,  # blue
        4: 0x03FF,  # yellow
        5: 0x7FFF,  # white
    }
    data = bytearray(6 * 16 * 2)
    for palette, bgr in colors.items():
        index = (palette * 16 + 1) * 2
        data[index] = bgr & 0xFF
        data[index + 1] = (bgr >> 8) & 0xFF
    return bytes(data)


def _emit(code: bytearray, *values: int) -> None:
    code.extend(values)


def build_snes_test_rom() -> bytes:
    """32KB LoROM. Reset draws the border pattern and waits."""
    rom = bytearray(32 * 1024)
    code = bytearray()
    # 65816 native, 8-bit A, 16-bit index. Blank, then BG1.
    start = [
        0x78, 0x18, 0xFB, 0xC2, 0x10, 0xE2, 0x20,
        0xA2, 0xFF, 0x1F, 0x9A,
        0xA9, 0x8F, 0x8D, 0x00, 0x21,  # force blank
        0x9C, 0x05, 0x21,              # mode 0
        0x9C, 0x07, 0x21,              # BG1 map at $0000
        0xA9, 0x01, 0x8D, 0x0B, 0x21,  # BG1 tiles at $1000
        0xA9, 0x01, 0x8D, 0x2C, 0x21,  # main screen BG1
        0x9C, 0x2D, 0x21,
        0xA9, 0x80, 0x8D, 0x15, 0x21,  # VRAM increment on high byte
    ]
    code.extend(start)
    # One solid 2bpp tile at VRAM word $1000. Eight rows of FF,00.
    code.extend([0xA2, 0x00, 0x10, 0x8E, 0x16, 0x21, 0xA0, 0x08, 0x00])
    tile_loop = len(code)
    code.extend([0xA9, 0xFF, 0x8D, 0x18, 0x21, 0x9C, 0x19, 0x21, 0x88])
    rel = tile_loop - (len(code) + 2)
    code.extend([0xD0, rel & 0xFF])
    # Tilemap from ROM $80:9000, 1024 words. Absolute LDA would hit WRAM.
    code.extend([
        0xA2, 0x00, 0x00, 0x8E, 0x16, 0x21,
        0xA2, 0x00, 0x00,
        0xA0, 0x00, 0x04,
    ])
    map_loop = len(code)
    code.extend([0xBF, 0x00, 0x90, 0x80, 0x8D, 0x18, 0x21, 0xE8, 0xBF, 0x00, 0x90, 0x80, 0x8D, 0x19, 0x21, 0xE8, 0x88])
    rel = map_loop - (len(code) + 2)
    code.extend([0xD0, rel & 0xFF])
    # CGRAM from ROM $80:8800, 192 bytes.
    code.extend([
        0xA9, 0x00, 0x8D, 0x21, 0x21,
        0xA2, 0x00, 0x00,
        0xA0, 0xC0, 0x00,
    ])
    cg_loop = len(code)
    code.extend([0xBF, 0x00, 0x88, 0x80, 0x8D, 0x22, 0x21, 0xE8, 0x88])
    rel = cg_loop - (len(code) + 2)
    code.extend([0xD0, rel & 0xFF])
    # Screen on, then wait.
    code.extend([0xA9, 0x0F, 0x8D, 0x00, 0x21, 0x80, 0xFE])
    if len(code) > 0x700:
        raise RuntimeError("test pattern code spilled into the data")
    rom[0:len(code)] = code
    rom[0x800:0x800 + len(_cgram())] = _cgram()  # CPU $8800
    tilemap = _tilemap()
    rom[0x1000:0x1000 + len(tilemap)] = tilemap  # CPU $9000
    title = b"BUDDY SNES TEST ROM  "
    rom[0x7FC0:0x7FC0 + 21] = title
    rom[0x7FD5:0x7FDC] = bytes([0x20, 0x00, 0x05, 0x00, 0x01, 0x00, 0x00])
    rom[0x7FE4:0x7FF0] = bytes([0x2C, 0x80, 0x2C, 0x80, 0x2C, 0x80, 0x2C, 0x80, 0x00, 0x00, 0x2C, 0x80])
    rom[0x7FF4:0x8000] = bytes([0x2C, 0x80, 0x00, 0x00, 0x2C, 0x80, 0x2C, 0x80, 0x00, 0x80, 0x2C, 0x80])
    return bytes(rom)
