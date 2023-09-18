"""Input classes."""

from boneio.input.gpio import GpioEventButton as GpioEventButtonOld
from boneio.input.gpio_new import GpioEventButtonNew


__all__ = ["GpioEventButtonOld", "GpioEventButtonNew"]
