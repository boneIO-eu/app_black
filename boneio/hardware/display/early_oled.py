"""Early OLED display for status and error messages.

This module provides standalone OLED functions that work independently
of the main boneIO application. The OLED is initialized as early as
possible so it can display:
- Boot progress messages
- Configuration errors
- Runtime crash information
- Shutdown messages

The early OLED device is later passed to the full DisplayManager
to avoid reinitializing the I2C bus.
"""

from __future__ import annotations

import logging
import textwrap
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Module-level singleton: initialized once, reused everywhere
_early_device: Any | None = None
_fonts: dict[str, Any] | None = None
_taken_over: bool = False  # Set True when DisplayManager takes control


def _get_fonts() -> dict[str, Any] | None:
    """Lazily load fonts for OLED display.

    Returns:
        Dictionary with font objects keyed by size name, or None if
        no font libraries are available (PIL/Pillow not installed).
    """
    global _fonts
    if _fonts is not None:
        return _fonts

    try:
        from boneio.core.utils.font_util import make_font

        _fonts = {
            "big": make_font("DejaVuSans.ttf", 12),
            "small": make_font("DejaVuSans.ttf", 9),
            "extraSmall": make_font("DejaVuSans.ttf", 7),
            "danube": make_font("danube__.ttf", 15, local=True),
        }
    except (OSError, ImportError):
        try:
            from PIL import ImageFont

            _LOGGER.debug("TTF fonts not found, using default PIL fonts")
            _fonts = {
                "big": ImageFont.load_default(),
                "small": ImageFont.load_default(),
                "extraSmall": ImageFont.load_default(),
                "danube": ImageFont.load_default(),
            }
        except ImportError:
            _LOGGER.debug("PIL not available, OLED text rendering disabled")
            return None
    return _fonts


def init_early_oled() -> Any | None:
    """Initialize bare OLED device for startup status messages.

    Creates the I2C connection and SH1106 device early, before the Manager
    or even config validation. This allows displaying boot progress,
    config errors, and crash info on the OLED screen.

    Call this once at the very start of the application.

    Returns:
        sh1106 device instance or None if OLED hardware is not available.
    """
    global _early_device
    if _early_device is not None:
        return _early_device

    try:
        from luma.core.interface.serial import i2c
        from luma.oled.device import sh1106

        serial = i2c(port=2, address=0x3C)
        _early_device = sh1106(serial)
        _LOGGER.debug("Early OLED device initialized for startup messages")
        return _early_device
    except Exception as err:
        _LOGGER.debug("Early OLED init skipped (no hardware): %s", err)
        return None


def get_early_device() -> Any | None:
    """Get the early-initialized OLED device singleton.

    Returns:
        sh1106 device instance or None if not initialized.
    """
    return _early_device


def handoff() -> None:
    """Signal that DisplayManager has taken over the OLED.

    After this call, draw_status/draw_error/draw_config_error become no-ops.
    Only draw_crash still works (safety — must always show fatal errors).
    """
    global _taken_over
    _taken_over = True
    _LOGGER.debug("Early OLED handed off to DisplayManager")


def is_taken_over() -> bool:
    """Check if DisplayManager has taken over the OLED."""
    return _taken_over


def draw_status(message: str, device: Any | None = None) -> None:
    """Draw a startup/status message on the OLED display.

    Shows the boneIO logo at the top and a status line below.

    Args:
        message: Status message to display (max ~20 chars for good readability).
        device: Optional device override; uses singleton if not provided.
    """
    dev = device or _early_device
    if dev is None or _taken_over:
        return
    try:
        from luma.core.render import canvas

        fonts = _get_fonts()
        if fonts is None:
            return
        with canvas(dev) as draw:
            draw.text((3, 3), "bone", font=fonts["danube"], fill=1)
            draw.text((53, 3), "iO", font=fonts["danube"], fill=1)
            draw.text((3, 30), message, font=fonts["small"], fill=1)
    except Exception as err:
        _LOGGER.debug("Failed to draw status on OLED: %s", err)


def draw_error(title: str, detail: str, device: Any | None = None) -> None:
    """Draw an error message on the OLED display.

    Shows a warning icon, error title, and up to 4 lines of wrapped detail.
    The screen stays visible until manually cleared or the app restarts.

    Args:
        title: Short error title (e.g., "Config Error", "Runtime Error").
        detail: Detailed error description (will be word-wrapped).
        device: Optional device override; uses singleton if not provided.
    """
    dev = device or _early_device
    if dev is None or _taken_over:
        return
    try:
        from luma.core.render import canvas

        fonts = _get_fonts()
        if fonts is None:
            return

        # Wrap detail text to fit ~25 chars per line
        wrapped = textwrap.wrap(detail, width=25)[:4]  # Max 4 lines

        with canvas(dev) as draw:
            # Warning triangle icon
            draw.polygon([(64, 1), (54, 14), (74, 14)], outline=1)
            draw.text((61, 3), "!", font=fonts["small"], fill=1)

            # Error title
            draw.text((3, 17), title, font=fonts["big"], fill=1)

            # Detail lines
            y = 32
            for line in wrapped:
                draw.text((3, y), line, font=fonts["extraSmall"], fill=1)
                y += 9

    except Exception as err:
        _LOGGER.debug("Failed to draw error on OLED: %s", err)


def draw_config_error(error_message: str, device: Any | None = None) -> None:
    """Draw a configuration error on the OLED display.

    Specialized version of draw_error for config validation failures.

    Args:
        error_message: The configuration error description.
        device: Optional device override; uses singleton if not provided.
    """
    draw_error(
        title="Config Error",
        detail=error_message,
        device=device,
    )


def draw_crash(exception: BaseException, device: Any | None = None) -> None:
    """Draw a crash/runtime error on the OLED display.

    This function ALWAYS works, even after handoff() — crashes must be
    visible to the user regardless of which component owns the screen.

    Args:
        exception: The exception that caused the crash.
        device: Optional device override; uses singleton if not provided.
    """
    global _taken_over
    was_taken_over = _taken_over
    _taken_over = False  # Temporarily unlock so draw_error works
    try:
        exc_type = type(exception).__name__
        exc_msg = str(exception) or "Unknown error"
        draw_error(
            title=f"ERROR: {exc_type}",
            detail=exc_msg,
            device=device,
        )
    finally:
        _taken_over = was_taken_over


def clear_display(device: Any | None = None) -> None:
    """Clear the OLED display (turn all pixels off).

    Args:
        device: Optional device override; uses singleton if not provided.
    """
    dev = device or _early_device
    if dev is None:
        return
    try:
        from luma.core.render import canvas

        with canvas(dev) as draw:
            draw.rectangle([0, 0, 127, 63], outline=0, fill=0)
    except Exception as err:
        _LOGGER.debug("Failed to clear OLED: %s", err)
