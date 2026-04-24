#!/usr/bin/env python3
"""Display a centered message on optional SH1106 OLED.

This script is safe to call when no OLED is connected or dependencies are
missing: it exits quietly with code 0.
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    lines = [line[:24] for line in argv[1:5] if line]
    if not lines:
        return 0

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
