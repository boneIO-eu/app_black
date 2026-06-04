#!/usr/bin/env python3
"""Display a centered message on optional SH1106 OLED.

Supports two modes:
  - Direct:  oled_msg.py "Line 1" "Line 2"   — one-shot render (slow, flickers)
  - Daemon:  oled_msg.py --serve              — keeps luma in memory, reads
             commands from /tmp/.oled_fifo (fast, no flicker)

When the daemon is running, direct calls detect it and send messages
through the FIFO instead of re-initializing luma.

This script is safe to call when no OLED is connected or dependencies are
missing: it exits quietly with code 0.
"""

from __future__ import annotations

import os
import sys

_FIFO_PATH = "/tmp/.oled_fifo"
_PID_PATH = "/tmp/.oled_serve.pid"


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


def _is_daemon_running() -> bool:
    """Check if the oled_msg daemon is running.

    Returns:
        True if daemon PID file exists and process is alive.
    """
    try:
        with open(_PID_PATH) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # Check if process exists
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False


def _send_to_daemon(lines: list[str]) -> bool:
    """Send a message to the running daemon via FIFO.

    Args:
        lines: List of text lines to display.

    Returns:
        True if message was sent successfully.
    """
    try:
        # Open FIFO in non-blocking write to avoid hanging if daemon died
        fd = os.open(_FIFO_PATH, os.O_WRONLY | os.O_NONBLOCK)
        msg = "|".join(lines) + "\n"
        os.write(fd, msg.encode())
        os.close(fd)
        return True
    except (OSError, BrokenPipeError):
        return False


def _draw(device, font, lines: list[str]) -> None:
    """Draw centered text lines on the OLED.

    Args:
        device: luma sh1106 device instance.
        font: PIL ImageFont instance.
        lines: List of 1-4 text strings to display.
    """
    from luma.core.render import canvas

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
            draw.text(positions[index], line[:24], font=font, fill="white")


def _serve() -> int:
    """Run as a daemon: initialize luma once, then listen on FIFO for commands.

    Message format on FIFO: "Line 1|Line 2|Line 3\\n"
    Special messages: "clear\\n" to clear display, "quit\\n" to stop daemon.

    Returns:
        Exit code.
    """
    _fast_clear_oled()

    try:
        from luma.core.interface.serial import i2c
        from luma.oled.device import sh1106
        from PIL import ImageFont
    except Exception:
        return 0

    try:
        serial = i2c(port=2, address=0x3C)
        device = sh1106(serial)
        device.persist = True
        font = ImageFont.load_default()
    except Exception:
        return 0

    # Create FIFO
    try:
        os.unlink(_FIFO_PATH)
    except FileNotFoundError:
        pass
    os.mkfifo(_FIFO_PATH)

    # Write PID file
    with open(_PID_PATH, "w") as f:
        f.write(str(os.getpid()))

    try:
        while True:
            # Open FIFO — blocks until a writer connects
            with open(_FIFO_PATH) as fifo:
                for raw_line in fifo:
                    msg = raw_line.strip()
                    if not msg:
                        continue
                    if msg == "quit":
                        return 0
                    if msg == "clear":
                        _fast_clear_oled()
                        continue
                    lines = msg.split("|")
                    _draw(device, font, lines)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.unlink(_FIFO_PATH)
        except FileNotFoundError:
            pass
        try:
            os.unlink(_PID_PATH)
        except FileNotFoundError:
            pass

    return 0


def main(argv: list[str]) -> int:
    """Display a centered message on optional SH1106 OLED.

    If --serve is passed, runs as a daemon listening on a FIFO.
    Otherwise, sends message to daemon if running, or falls back
    to direct luma rendering.

    Args:
        argv: Command-line arguments.

    Returns:
        Exit code (always 0).
    """
    if len(argv) > 1 and argv[1] == "--serve":
        return _serve()

    lines = [line[:24] for line in argv[1:5] if line]
    if not lines:
        return 0

    # Try sending to daemon first (fast path — no Python init overhead)
    if _is_daemon_running() and _send_to_daemon(lines):
        return 0

    # Fallback: direct rendering (slow but always works)
    _fast_clear_oled()

    try:
        from luma.core.error import DeviceNotFoundError
        from luma.core.interface.serial import i2c
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
        _draw(device, ImageFont.load_default(), lines)
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

