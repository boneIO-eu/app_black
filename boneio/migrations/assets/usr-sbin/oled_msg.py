#!/usr/bin/env python3
"""Display a centered message on optional SH1106 OLED.

This script is safe to call when no OLED is connected or dependencies are
missing: it exits quietly with code 0.
"""

from __future__ import annotations

import sys


def _fast_clear_oled() -> None:
    """Clear OLED display via raw I2C before slow luma init.

    On soft-reboot the SH1106 retains the previous image. Luma's sh1106()
    constructor takes ~9 seconds (device enumeration, contrast setup, etc.).
    This function clears the display in ~50ms using raw smbus2 writes,
    so the stale image disappears almost instantly at boot.
    """
    try:
        import smbus2

        bus = smbus2.SMBus(2)
        addr = 0x3C
        # SH1106 init: display on, set page addressing
        for cmd in [
            0xAE,
            0xD5,
            0x80,
            0xA8,
            0x3F,
            0xD3,
            0x00,
            0x40,
            0xAD,
            0x8B,
            0xA1,
            0xC8,
            0xDA,
            0x12,
            0x81,
            0xFF,
            0xD9,
            0x1F,
            0xDB,
            0x40,
            0xA6,
            0xAF,
        ]:
            bus.write_byte_data(addr, 0x00, cmd)
        # Clear all 8 pages (128 columns each)
        blank = [0x00] * 128
        for page in range(8):
            bus.write_byte_data(addr, 0x00, 0xB0 | page)  # set page
            bus.write_byte_data(addr, 0x00, 0x02)  # low col (offset 2 for SH1106)
            bus.write_byte_data(addr, 0x00, 0x10)  # high col
            # Write in chunks of 32 (smbus limit)
            for i in range(0, 128, 32):
                bus.write_i2c_block_data(addr, 0x40, blank[i : i + 32])
        bus.close()
    except Exception:
        pass  # No OLED or smbus2 not available — ignore


def main(argv: list[str]) -> int:
    lines = [line[:24] for line in argv[1:5] if line]
    if not lines:
        return 0

    # Immediately clear stale OLED content (e.g. "has stopped" from previous session)
    _fast_clear_oled()

    try:
        from luma.core.error import DeviceNotFoundError
        from luma.core.interface.serial import i2c
        from luma.core.render import canvas
        from luma.oled.device import sh1106
        from PIL import ImageFont
    except Exception:
        return 0

    try:
        serial = i2c(port=2, address=0x3C)
        device = sh1106(serial)
        device.persist = True
    except (DeviceNotFoundError, OSError, Exception):
        return 0

    try:
        font = ImageFont.load_default()
        with canvas(device) as draw:
            if len(lines) == 1:
                positions = [(20, 26)]
            elif len(lines) == 2:
                positions = [(12, 20), (12, 36)]
            elif len(lines) == 3:
                positions = [(8, 12), (8, 28), (8, 44)]
            else:
                positions = [(4, 4), (4, 18), (4, 32), (4, 46)]
            for index, line in enumerate(lines):
                draw.text(positions[index], line, font=font, fill="white")
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
