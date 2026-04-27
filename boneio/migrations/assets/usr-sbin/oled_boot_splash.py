#!/usr/bin/env python3
"""Ultra-fast OLED boot splash using raw smbus2 (no luma, no PIL).

Starts in <200ms vs ~9s for luma-based oled_msg.py.
Uses a built-in 5x8 font and direct SH1106 I2C page writes.

Usage: oled_boot_splash.py "Line 1" ["Line 2"] ["Line 3"] ["Line 4"]
"""

from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# SH1106 constants
# ---------------------------------------------------------------------------
_ADDR = 0x3C
_I2C_BUS = 2
_WIDTH = 128
_PAGES = 8  # 64px / 8
_COL_OFFSET = 2  # SH1106 has 132-column RAM, display starts at col 2

# ---------------------------------------------------------------------------
# 5x8 font — printable ASCII (chars 32–126)
# Each character is 5 bytes (columns), MSB = bottom pixel row.
# Standard GLCD font, widely used in embedded/Arduino projects.
# ---------------------------------------------------------------------------
_FONT = (
    b"\x00\x00\x00\x00\x00"  # 32 (space)
    b"\x00\x00\x5f\x00\x00"  # 33 !
    b"\x00\x07\x00\x07\x00"  # 34 "
    b"\x14\x7f\x14\x7f\x14"  # 35 #
    b"\x24\x2a\x7f\x2a\x12"  # 36 $
    b"\x23\x13\x08\x64\x62"  # 37 %
    b"\x36\x49\x55\x22\x50"  # 38 &
    b"\x00\x05\x03\x00\x00"  # 39 '
    b"\x00\x1c\x22\x41\x00"  # 40 (
    b"\x00\x41\x22\x1c\x00"  # 41 )
    b"\x14\x08\x3e\x08\x14"  # 42 *
    b"\x08\x08\x3e\x08\x08"  # 43 +
    b"\x00\x50\x30\x00\x00"  # 44 ,
    b"\x08\x08\x08\x08\x08"  # 45 -
    b"\x00\x60\x60\x00\x00"  # 46 .
    b"\x20\x10\x08\x04\x02"  # 47 /
    b"\x3e\x51\x49\x45\x3e"  # 48 0
    b"\x00\x42\x7f\x40\x00"  # 49 1
    b"\x42\x61\x51\x49\x46"  # 50 2
    b"\x21\x41\x45\x4b\x31"  # 51 3
    b"\x18\x14\x12\x7f\x10"  # 52 4
    b"\x27\x45\x45\x45\x39"  # 53 5
    b"\x3c\x4a\x49\x49\x30"  # 54 6
    b"\x01\x71\x09\x05\x03"  # 55 7
    b"\x36\x49\x49\x49\x36"  # 56 8
    b"\x06\x49\x49\x29\x1e"  # 57 9
    b"\x00\x36\x36\x00\x00"  # 58 :
    b"\x00\x56\x36\x00\x00"  # 59 ;
    b"\x08\x14\x22\x41\x00"  # 60 <
    b"\x14\x14\x14\x14\x14"  # 61 =
    b"\x00\x41\x22\x14\x08"  # 62 >
    b"\x02\x01\x51\x09\x06"  # 63 ?
    b"\x32\x49\x79\x41\x3e"  # 64 @
    b"\x7e\x11\x11\x11\x7e"  # 65 A
    b"\x7f\x49\x49\x49\x36"  # 66 B
    b"\x3e\x41\x41\x41\x22"  # 67 C
    b"\x7f\x41\x41\x22\x1c"  # 68 D
    b"\x7f\x49\x49\x49\x41"  # 69 E
    b"\x7f\x09\x09\x09\x01"  # 70 F
    b"\x3e\x41\x49\x49\x7a"  # 71 G
    b"\x7f\x08\x08\x08\x7f"  # 72 H
    b"\x00\x41\x7f\x41\x00"  # 73 I
    b"\x20\x40\x41\x3f\x01"  # 74 J
    b"\x7f\x08\x14\x22\x41"  # 75 K
    b"\x7f\x40\x40\x40\x40"  # 76 L
    b"\x7f\x02\x0c\x02\x7f"  # 77 M
    b"\x7f\x04\x08\x10\x7f"  # 78 N
    b"\x3e\x41\x41\x41\x3e"  # 79 O
    b"\x7f\x09\x09\x09\x06"  # 80 P
    b"\x3e\x41\x51\x21\x5e"  # 81 Q
    b"\x7f\x09\x19\x29\x46"  # 82 R
    b"\x46\x49\x49\x49\x31"  # 83 S
    b"\x01\x01\x7f\x01\x01"  # 84 T
    b"\x3f\x40\x40\x40\x3f"  # 85 U
    b"\x1f\x20\x40\x20\x1f"  # 86 V
    b"\x3f\x40\x38\x40\x3f"  # 87 W
    b"\x63\x14\x08\x14\x63"  # 88 X
    b"\x07\x08\x70\x08\x07"  # 89 Y
    b"\x61\x51\x49\x45\x43"  # 90 Z
    b"\x00\x7f\x41\x41\x00"  # 91 [
    b"\x02\x04\x08\x10\x20"  # 92 backslash
    b"\x00\x41\x41\x7f\x00"  # 93 ]
    b"\x04\x02\x01\x02\x04"  # 94 ^
    b"\x40\x40\x40\x40\x40"  # 95 _
    b"\x00\x01\x02\x04\x00"  # 96 `
    b"\x20\x54\x54\x54\x78"  # 97 a
    b"\x7f\x48\x44\x44\x38"  # 98 b
    b"\x38\x44\x44\x44\x20"  # 99 c
    b"\x38\x44\x44\x48\x7f"  # 100 d
    b"\x38\x54\x54\x54\x18"  # 101 e
    b"\x08\x7e\x09\x01\x02"  # 102 f
    b"\x18\xa4\xa4\xa4\x7c"  # 103 g
    b"\x7f\x08\x04\x04\x78"  # 104 h
    b"\x00\x44\x7d\x40\x00"  # 105 i
    b"\x20\x40\x44\x3d\x00"  # 106 j
    b"\x7f\x10\x28\x44\x00"  # 107 k
    b"\x00\x41\x7f\x40\x00"  # 108 l
    b"\x7c\x04\x18\x04\x78"  # 109 m
    b"\x7c\x08\x04\x04\x78"  # 110 n
    b"\x38\x44\x44\x44\x38"  # 111 o
    b"\x7c\x14\x14\x14\x08"  # 112 p
    b"\x08\x14\x14\x18\x7c"  # 113 q
    b"\x7c\x08\x04\x04\x08"  # 114 r
    b"\x48\x54\x54\x54\x20"  # 115 s
    b"\x04\x3f\x44\x40\x20"  # 116 t
    b"\x3c\x40\x40\x20\x7c"  # 117 u
    b"\x1c\x20\x40\x20\x1c"  # 118 v
    b"\x3c\x40\x30\x40\x3c"  # 119 w
    b"\x44\x28\x10\x28\x44"  # 120 x
    b"\x0c\x50\x50\x50\x3c"  # 121 y
    b"\x44\x64\x54\x4c\x44"  # 122 z
    b"\x00\x08\x36\x41\x00"  # 123 {
    b"\x00\x00\x7f\x00\x00"  # 124 |
    b"\x00\x41\x36\x08\x00"  # 125 }
    b"\x10\x08\x08\x10\x08"  # 126 ~
)

_CHAR_W = 6  # 5px glyph + 1px spacing


def _render_line(text: str, max_chars: int = 21) -> list[int]:
    """Render a text line to a list of column bytes (1 page tall).

    Args:
        text: ASCII string to render.
        max_chars: Maximum characters that fit in 128px width.

    Returns:
        List of 128 byte values representing one page of pixel columns.
    """
    text = text[:max_chars]
    buf = [0] * _WIDTH
    x = 0
    for ch in text:
        idx = ord(ch) - 32
        if idx < 0 or idx >= 95:
            idx = 0  # fallback to space
        offset = idx * 5
        for col in range(5):
            if x < _WIDTH:
                buf[x] = _FONT[offset + col]
                x += 1
        if x < _WIDTH:
            buf[x] = 0  # 1px spacing
            x += 1
    return buf


def main(argv: list[str]) -> int:
    """Display boot splash message on SH1106 OLED via raw I2C.

    Args:
        argv: Command line arguments (lines of text to display).

    Returns:
        0 on success, 0 on any error (silent fail — no OLED is OK).
    """
    lines = [line[:21] for line in argv[1:5] if line]
    if not lines:
        return 0

    try:
        import smbus2
    except ImportError:
        print("smbus2 not available", file=sys.stderr)
        return 0

    try:
        bus = smbus2.SMBus(_I2C_BUS)
    except OSError:
        return 0

    try:
        # SH1106 initialization sequence
        init_cmds = [
            0xAE,  # display off
            0xD5,
            0x80,  # set clock div
            0xA8,
            0x3F,  # set multiplex (64-1)
            0xD3,
            0x00,  # set display offset
            0x40,  # set start line 0
            0xAD,
            0x8B,  # set charge pump (internal DC-DC)
            0xA1,  # segment remap (flip horizontal)
            0xC8,  # COM scan direction (flip vertical)
            0xDA,
            0x12,  # set COM pins
            0x81,
            0xFF,  # set contrast (max)
            0xD9,
            0x1F,  # set precharge
            0xDB,
            0x40,  # set VCOMH deselect
            0xA6,  # normal display (not inverted)
            0xAF,  # display on
        ]
        for cmd in init_cmds:
            bus.write_byte_data(_ADDR, 0x00, cmd)

        # Calculate vertical positioning (center lines on display)
        if len(lines) == 1:
            page_starts = [3]
        elif len(lines) == 2:
            page_starts = [2, 5]
        elif len(lines) == 3:
            page_starts = [1, 3, 6]
        else:
            page_starts = [0, 2, 4, 6]

        # Clear display and render text
        blank = [0x00] * 32
        for page in range(_PAGES):
            bus.write_byte_data(_ADDR, 0x00, 0xB0 | page)
            bus.write_byte_data(_ADDR, 0x00, _COL_OFFSET & 0x0F)
            bus.write_byte_data(_ADDR, 0x00, 0x10 | (_COL_OFFSET >> 4))
            for i in range(0, _WIDTH, 32):
                bus.write_i2c_block_data(_ADDR, 0x40, blank)

        # Write text lines
        for line_idx, text in enumerate(lines):
            page = page_starts[line_idx]
            pixels = _render_line(text)

            # Center horizontally
            text_width = min(len(text), 21) * _CHAR_W
            x_offset = (_WIDTH - text_width) // 2
            # Shift pixel data
            centered = [0] * x_offset + pixels[:text_width] + [0] * (_WIDTH - x_offset - text_width)
            centered = centered[:_WIDTH]

            bus.write_byte_data(_ADDR, 0x00, 0xB0 | page)
            bus.write_byte_data(_ADDR, 0x00, _COL_OFFSET & 0x0F)
            bus.write_byte_data(_ADDR, 0x00, 0x10 | (_COL_OFFSET >> 4))
            for i in range(0, _WIDTH, 32):
                chunk = centered[i : i + 32]
                bus.write_i2c_block_data(_ADDR, 0x40, chunk)

        bus.close()
    except Exception as exc:
        print(f"OLED error: {exc}", file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
