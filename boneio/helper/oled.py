import os

from PIL import ImageFont

from boneio.const import FONTS


def make_font(name: str, size: int, local: bool = False):
    """Prepare ImageFont for Oled screen."""
    font_path = (
        name
        if not local
        else os.path.join(os.path.dirname(__file__), "..", FONTS, name)
    )
    return ImageFont.truetype(font_path, size)
