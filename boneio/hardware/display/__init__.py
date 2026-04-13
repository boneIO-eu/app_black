"""Display hardware components."""

from boneio.hardware.display.early_oled import (
    clear_display,
    draw_config_error,
    draw_crash,
    draw_error,
    draw_status,
    get_early_device,
    handoff,
    init_early_oled,
    is_taken_over,
)

# Oled class requires luma (I2C hardware). Import lazily to avoid
# ImportError when only early_oled functions are needed.
try:
    from boneio.hardware.display.oled import Oled
except ImportError:
    Oled = None  # type: ignore[misc,assignment]

__all__ = [
    "Oled",
    "clear_display",
    "draw_config_error",
    "draw_crash",
    "draw_error",
    "draw_status",
    "get_early_device",
    "handoff",
    "init_early_oled",
    "is_taken_over",
]
