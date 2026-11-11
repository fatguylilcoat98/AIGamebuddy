"""A 256x224 Super NES test pattern.

The startup is the register clear from the backdrop ROM that already displayed
on the Windows runner. Palettes are stored with direct $2122 writes, then one
solid tile and a border tilemap. The backdrop stays blue if the tiles miss.
It is public domain and is not shipped in the installer.
"""
from __future__ import annotations


def _rel(origin: int, here: int) -> int:
    value = origin - (here + 2)
    if not -128 <= value <= 127:
        raise RuntimeError(f"branch from {here} to {origin} does not fit")
    return value & 0xFF


def build_snes_test_rom() -> bytes:
    """32KB LoROM. Reset draws a colored border and waits."""
    rom = bytearray(32 * 1024)
    code = bytearray([
        0x78, 0x18, 0xFB,
        0xC2, 0x10, 0xE2, 0x20,
        0xA2, 0xFF, 0x1F, 0x9A,
        0xA2, 0x33, 0x00,
        0x9E, 0x00, 0x21,
        0x9E, 0x00, 0x42,
        0xCA, 0x10, 0xF7,
        0xA9, 0x80, 0x8D, 0x00, 0x21,  # force blank
        0x9C, 0x05, 0x21,              # mode 0
        0x9C, 0x07, 0x21,              # BG1 map $0000
        0xA9, 0x01, 0x8D, 0x0B, 0x21,  # BG1 tiles $1000
        0xA9, 0x01, 0x8D, 0x2C, 0x21,  # BG1 on
        0x9C, 0x2D, 0x21,
        0xA9, 0x80, 0x8D, 0x15, 0x21,  # increment on high byte
    ])
    # One solid color-1 tile at VRAM word $1000.
    code.extend([0xA2, 0x00, 0x10, 0x8E, 0x16, 0x21, 0xA0, 0x08, 0x00])
    tile_loop = len(code)
    code.extend([0xA9, 0xFF, 0x8D, 0x18, 0x21, 0x9C, 0x19, 0x21, 0x88])
    code.extend([0xD0, _rel(tile_loop, len(code))])
    # Tilemap from $80:9000, 1024 words. Absolute LDA would hit WRAM.
    code.extend([0xA2, 0x00, 0x00, 0x8E, 0x16, 0x21, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x04])
    map_loop = len(code)
    code.extend([
        0xBF, 0x00, 0x90, 0x80, 0x8D, 0x18, 0x21, 0xE8,
        0xBF, 0x00, 0x90, 0x80, 0x8D, 0x19, 0x21, 0xE8, 0x88,
    ])
    code.extend([0xD0, _rel(map_loop, len(code))])
    # Named colors, written straight to CGRAM. Index 0 is the backdrop.
    writes = [
        (0, 0x7C00),    # blue backdrop
        (17, 0x001F),   # palette 1 color 1 red
        (33, 0x03E0),   # palette 2 color 1 green
        (49, 0x7C00),   # palette 3 color 1 blue
        (65, 0x03FF),   # palette 4 color 1 yellow
        (81, 0x7FFF),   # palette 5 color 1 white
    ]
    for index, color in writes:
        code.extend([
            0xA9, index & 0xFF, 0x8D, 0x21, 0x21,
            0xA9, color & 0xFF, 0x8D, 0x22, 0x21,
            0xA9, (color >> 8) & 0xFF, 0x8D, 0x22, 0x21,
        ])
    code.extend([0xA9, 0x0F, 0x8D, 0x00, 0x21])  # screen on
    jmp_at = len(code)
    code.extend([0x4C, jmp_at & 0xFF, 0x80])
    if len(code) > 0x1000:
        raise RuntimeError("test pattern code spilled into the tilemap")
    rom[0:len(code)] = code
    # Tilemap at file 0x1000 = CPU $80:9000. 32x32 words, visible area 32x28.
    for row in range(32):
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
            word = palette << 10
            at = 0x1000 + (row * 32 + col) * 2
            rom[at] = word & 0xFF
            rom[at + 1] = (word >> 8) & 0xFF
    title = b"BUDDY SNES TEST ROM  "
    rom[0x7FC0:0x7FC0 + 21] = title
    rom[0x7FD5:0x7FDC] = bytes([0x20, 0x00, 0x05, 0x00, 0x01, 0x00, 0x00])
    rom[len(code)] = 0x40  # RTI for stray interrupts
    rti = bytes([len(code) & 0xFF, 0x80])
    rom[0x7FE4:0x7FF0] = rti * 4 + bytes([0x00, 0x00]) + rti
    rom[0x7FF4:0x7FFC] = rti + bytes([0x00, 0x00]) + rti + rti
    rom[0x7FFC:0x7FFE] = bytes([0x00, 0x80])
    rom[0x7FFE:0x8000] = rti
    return bytes(rom)
