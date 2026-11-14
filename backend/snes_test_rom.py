"""A 256x224 Super NES test pattern.

Palette 0 only. Direct $2118/$2122 writes, the same path that already displayed
on Snes9x. Tile 0 is a dark cell with a yellow grid line. Tile 1 is a red
border. Tile 2 is a yellow border. The backdrop is not the blue backing, so a
missed tile cannot hide in the blue. Public domain. Not shipped.
"""
from __future__ import annotations


class _Asm:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def label(self, name: str) -> None:
        self.labels[name] = len(self.buf)

    def emit(self, *raw: int) -> None:
        self.buf.extend(raw)

    def branch(self, opcode: int, name: str) -> None:
        self.fixups.append((len(self.buf), name))
        self.emit(opcode, 0)

    def finish(self) -> bytes:
        for at, name in self.fixups:
            rel = self.labels[name] - (at + 2)
            if not -128 <= rel <= 127:
                raise RuntimeError(f"branch to {name} does not fit")
            self.buf[at + 1] = rel & 0xFF
        return bytes(self.buf)


def _solid_tile(code: _Asm, vram_word: int, plane0: int, plane1: int) -> None:
    code.emit(0xA2, vram_word & 0xFF, (vram_word >> 8) & 0xFF, 0x8E, 0x16, 0x21)
    row = bytes([0xA9, plane0, 0x8D, 0x18, 0x21, 0xA9, plane1, 0x8D, 0x19, 0x21])
    for _ in range(8):
        code.emit(*row)


def _grid_tile(code: _Asm) -> None:
    """8x8 cell. Left column and bottom row are color 3. The rest is color 2."""
    code.emit(0xA2, 0x00, 0x10, 0x8E, 0x16, 0x21)
    for row in range(8):
        if row == 7:
            plane0, plane1 = 0xFF, 0xFF
        else:
            # Bit 7 is the left pixel. Color 3 there, color 2 everywhere else.
            plane0, plane1 = 0x80, 0xFF
        code.emit(0xA9, plane0, 0x8D, 0x18, 0x21, 0xA9, plane1, 0x8D, 0x19, 0x21)


def build_snes_test_rom() -> bytes:
    """32KB LoROM. Reset draws the border grid and waits."""
    code = _Asm()
    code.emit(
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
        0xA9, 0x80, 0x8D, 0x15, 0x21,  # increment on the high byte
    )
    _grid_tile(code)                              # tile 0 at $1000
    _solid_tile(code, 0x1008, 0xFF, 0x00)         # tile 1 color 1
    _solid_tile(code, 0x1010, 0xFF, 0xFF)         # tile 2 color 3
    # 32x32 tilemap. Top and left are red, bottom and right are yellow.
    code.emit(0xA2, 0x00, 0x00, 0x8E, 0x16, 0x21, 0xA2, 0x00, 0x00)
    code.label("row")
    code.emit(0xA0, 0x00, 0x00)
    code.label("col")
    code.emit(0xA9, 0x00)
    code.emit(0xE0, 0x00, 0x00)
    code.branch(0xF0, "red")
    code.emit(0xE0, 0x1B, 0x00)  # row 27, the last visible row
    code.branch(0xF0, "yellow")
    code.emit(0xC0, 0x00, 0x00)
    code.branch(0xF0, "red")
    code.emit(0xC0, 0x1F, 0x00)  # column 31
    code.branch(0xF0, "yellow")
    code.branch(0x80, "store")
    code.label("red")
    code.emit(0xA9, 0x01)
    code.branch(0x80, "store")
    code.label("yellow")
    code.emit(0xA9, 0x02)
    code.label("store")
    code.emit(0x8D, 0x18, 0x21, 0x9C, 0x19, 0x21, 0xC8, 0xC0, 0x20, 0x00)
    code.branch(0xD0, "col")
    code.emit(0xE8, 0xE0, 0x20, 0x00)
    code.branch(0xD0, "row")
    # Color 0 black, 1 red, 2 dark plum, 3 yellow. Sequential, palette 0.
    code.emit(0xA9, 0x00, 0x8D, 0x21, 0x21)
    for color in (0x0000, 0x001F, 0x2008, 0x03FF):
        code.emit(0xA9, color & 0xFF, 0x8D, 0x22, 0x21, 0xA9, (color >> 8) & 0xFF, 0x8D, 0x22, 0x21)
    code.emit(0xA9, 0x01, 0x8D, 0x2C, 0x21)  # BG1 on
    code.emit(0xA9, 0x0F, 0x8D, 0x00, 0x21)  # screen on
    code.label("wait")
    code.emit(0x4C, 0x00, 0x80)
    program = bytearray(code.finish())
    wait_at = code.labels["wait"]
    # LoROM maps file offset N to CPU $8000+N, so the high byte is not always $80.
    address = 0x8000 + wait_at
    program[wait_at + 1] = address & 0xFF
    program[wait_at + 2] = (address >> 8) & 0xFF
    if len(program) > 0x8000:
        raise RuntimeError("test pattern does not fit in 32KB")
    rom = bytearray(32 * 1024)
    rom[0:len(program)] = program
    rom[0x7FC0:0x7FC0 + 21] = b"BUDDY SNES TEST ROM  "
    rom[0x7FD5:0x7FDC] = bytes([0x20, 0x00, 0x05, 0x00, 0x01, 0x00, 0x00])
    rti_at = len(program)
    rom[rti_at] = 0x40
    rti = bytes([rti_at & 0xFF, 0x80])
    rom[0x7FE4:0x7FF0] = rti * 4 + bytes([0x00, 0x00]) + rti
    rom[0x7FF4:0x7FFC] = rti + bytes([0x00, 0x00]) + rti + rti
    rom[0x7FFC:0x7FFE] = bytes([0x00, 0x80])
    rom[0x7FFE:0x8000] = rti
    return bytes(rom)
