"""A 256x224 Super NES test pattern.

The picture is 4:3. The left border and the right border are different colors,
so a stretched or missing picture fails the Windows check. The startup matches
the backdrop ROM that already displayed on the runner, then a DMA copies the
tiles. It is public domain and is not shipped in the installer.
"""
from __future__ import annotations


def _tile() -> bytes:
    """One solid 2bpp tile. Every pixel is color 1."""
    row = bytes([0xFF, 0x00])
    return row * 8


def _tilemap() -> bytes:
    """32 by 32 words. The visible 32 by 28 screen has different border palettes."""
    words = []
    for row in range(32):
        for col in range(32):
            if row == 0:
                palette = 1  # red
            elif row == 27:
                palette = 2  # green
            elif col == 0:
                palette = 3  # blue
            elif col == 31:
                palette = 4  # yellow
            else:
                palette = 5  # white
            words.append(palette << 10)
    out = bytearray()
    for word in words:
        out.append(word & 0xFF)
        out.append((word >> 8) & 0xFF)
    return bytes(out)


def _cgram() -> bytes:
    """Color 1 of palettes 1-5, plus a dim backdrop so a missed layer is not black."""
    colors = {
        0: 0x7C00,  # blue backdrop, the color the runner already displayed
        1: 0x001F,  # red
        2: 0x03E0,  # green
        3: 0x7C00,  # blue
        4: 0x03FF,  # yellow
        5: 0x7FFF,  # white
    }
    data = bytearray(6 * 16 * 2)
    for palette, bgr in colors.items():
        index = (palette * 16 + (0 if palette == 0 else 1)) * 2
        data[index] = bgr & 0xFF
        data[index + 1] = (bgr >> 8) & 0xFF
    return bytes(data)


def _dma(dest_vram: int, source: int, size: int, mode: int, port: int) -> list[int]:
    """One DMA from ROM bank $80 into a PPU port. Source is a CPU address."""
    return [
        0xA2, dest_vram & 0xFF, (dest_vram >> 8) & 0xFF, 0x8E, 0x16, 0x21,  # LDX dest / STX $2116
        0xA9, mode, 0x8D, 0x00, 0x43,   # DMA mode
        0xA9, port, 0x8D, 0x01, 0x43,   # DMA port
        0xA2, source & 0xFF, (source >> 8) & 0xFF, 0x8E, 0x02, 0x43,
        0xA9, 0x80, 0x8D, 0x04, 0x43,   # bank $80
        0xA2, size & 0xFF, (size >> 8) & 0xFF, 0x8E, 0x05, 0x43,
        0xA9, 0x01, 0x8D, 0x0B, 0x42,   # start DMA
    ]


def build_snes_test_rom() -> bytes:
    """32KB LoROM. Reset draws the border pattern and waits."""
    rom = bytearray(32 * 1024)
    # The same register clear the backdrop ROM used, then force blank.
    code = [
        0x78, 0x18, 0xFB,             # SEI / CLC / XCE
        0xC2, 0x10, 0xE2, 0x20,       # 16-bit index, 8-bit A
        0xA2, 0xFF, 0x1F, 0x9A,       # LDX #$1FFF / TXS
        0xA2, 0x33, 0x00,             # LDX #$0033
        0x9E, 0x00, 0x21,             # STZ $2100,X
        0x9E, 0x00, 0x42,             # STZ $4200,X
        0xCA,                         # DEX
        0x10, 0xF7,                   # BPL clear
        0xA9, 0x80, 0x8D, 0x00, 0x21, # force blank
        0xA9, 0x80, 0x8D, 0x15, 0x21, # VRAM increment on the high byte
        0x9C, 0x05, 0x21,             # mode 0
        0x9C, 0x07, 0x21,             # BG1 map at $0000
        0xA9, 0x01, 0x8D, 0x0B, 0x21, # BG1 tiles at $1000
        0xA9, 0x01, 0x8D, 0x2C, 0x21, # main screen BG1
        0x9C, 0x2D, 0x21,
        0x9C, 0x21, 0x21,             # CGRAM address 0
    ]
    # CPU $80:8000 is the start of this file. Data lives at file 0x1800 = $9800.
    code.extend(_dma(0x1000, 0x9800, 16, 0x01, 0x18))
    code.extend(_dma(0x0000, 0x9820, 0x800, 0x01, 0x18))
    code.extend([
        0xA9, 0x00, 0x8D, 0x00, 0x43,  # DMA mode 0, one byte
        0xA9, 0x22, 0x8D, 0x01, 0x43,
        0xA2, 0x00, 0xA1, 0x8E, 0x02, 0x43,  # source $A100
        0xA9, 0x80, 0x8D, 0x04, 0x43,
        0xA2, 0xC0, 0x00, 0x8E, 0x05, 0x43,
        0xA9, 0x01, 0x8D, 0x0B, 0x42,
        0xA9, 0x0F, 0x8D, 0x00, 0x21,  # screen on
        0x4C, 0x00, 0x80,             # JMP $8000 would reset; jump to self below
    ])
    # Patch the final JMP to the address of this JMP, so it waits.
    jmp_at = len(code) - 3
    code[jmp_at + 1] = jmp_at & 0xFF
    code[jmp_at + 2] = 0x80
    if len(code) > 0x1700:
        raise RuntimeError("test pattern code spilled into the data")
    rom[0:len(code)] = bytes(code)
    rom[0x1800:0x1800 + 16] = _tile()
    rom[0x1820:0x1820 + 0x800] = _tilemap()
    rom[0x2100:0x2100 + 0xC0] = _cgram()
    title = b"BUDDY SNES TEST ROM  "
    rom[0x7FC0:0x7FC0 + 21] = title
    rom[0x7FD5:0x7FDC] = bytes([0x20, 0x00, 0x05, 0x00, 0x01, 0x00, 0x00])
    # Non-reset vectors land on an RTI so a stray interrupt cannot eat the setup.
    rom[len(code)] = 0x40
    rti = len(code)
    rti_bytes = bytes([rti & 0xFF, 0x80])
    rom[0x7FE4:0x7FF0] = rti_bytes * 4 + bytes([0x00, 0x00]) + rti_bytes
    rom[0x7FF4:0x7FFC] = rti_bytes + bytes([0x00, 0x00]) + rti_bytes + rti_bytes
    rom[0x7FFC:0x7FFE] = bytes([0x00, 0x80])
    rom[0x7FFE:0x8000] = rti_bytes
    return bytes(rom)
