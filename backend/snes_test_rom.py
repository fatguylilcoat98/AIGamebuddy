"""A tiny Super NES ROM Buddy generates for the Windows test.

It is Buddy's own program: a solid blue screen, public domain, not a game
anybody owns. The Windows run uses it so RetroArch has a picture inside the
frame. It is not shipped inside BuddySetup.exe.
"""
from __future__ import annotations


def build_snes_test_rom() -> bytes:
    """32KB LoROM. Reset fills the backdrop with blue and waits."""
    rom = bytearray(32 * 1024)
    code = bytes([
        0x78,             # SEI
        0x18,             # CLC
        0xFB,             # XCE
        0xC2, 0x10,       # REP #$10   X/Y 16-bit
        0xE2, 0x20,       # SEP #$20   A 8-bit
        0xA2, 0xFF, 0x1F, # LDX #$1FFF
        0x9A,             # TXS
        0xA2, 0x33, 0x00, # LDX #$0033
        0x9E, 0x00, 0x21, # STZ $2100,X
        0x9E, 0x00, 0x42, # STZ $4200,X
        0xCA,             # DEX
        0x10, 0xF7,       # BPL clear
        0x9C, 0x21, 0x21, # STZ $2121  palette 0
        0xA9, 0x00,       # LDA #$00   blue, low byte
        0x8D, 0x22, 0x21, # STA $2122
        0xA9, 0x7C,       # LDA #$7C   blue, high byte
        0x8D, 0x22, 0x21, # STA $2122
        0xA9, 0x0F,       # LDA #$0F   screen on
        0x8D, 0x00, 0x21, # STA $2100
        0x4C, 0x29, 0x80, # JMP forever
        0x4C, 0x2C, 0x80, # JMP trap
    ])
    rom[0:len(code)] = code
    title = b"BUDDY SNES TEST ROM  "
    if len(title) != 21:
        raise RuntimeError("SNES title must be 21 bytes")
    rom[0x7FC0:0x7FC0 + 21] = title
    rom[0x7FD5:0x7FDC] = bytes([0x20, 0x00, 0x05, 0x00, 0x01, 0x00, 0x00])
    # Native vectors, then emulation vectors. Reset is $8000. Trap is $802C.
    rom[0x7FE4:0x7FF0] = bytes([
        0x2C, 0x80, 0x2C, 0x80, 0x2C, 0x80, 0x2C, 0x80, 0x00, 0x00, 0x2C, 0x80,
    ])
    rom[0x7FF4:0x8000] = bytes([
        0x2C, 0x80, 0x00, 0x00, 0x2C, 0x80, 0x2C, 0x80, 0x00, 0x80, 0x2C, 0x80,
    ])
    return bytes(rom)
