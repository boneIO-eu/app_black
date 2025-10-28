"""Font utilities for display rendering."""

import os

from PIL import ImageFont


def make_font(name: str, size: int, local: bool = False):
    """Prepare ImageFont for OLED screen.
    
    Args:
        name: Font filename (for local) or system font name
        size: Font size in points
        local: If True, load from hardware/display/fonts/, else use system font
        
    Returns:
        PIL ImageFont object
        
    Raises:
        OSError: If font file is not found
    """
    if local:
        # Load from local fonts directory (hardware/display/fonts/)
        font_path = os.path.join(
            os.path.dirname(__file__), 
            "..", "..", "hardware", "display", "fonts", 
            name
        )
    else:
        # Use system font
        font_path = name
    
    return ImageFont.truetype(font_path, size)
