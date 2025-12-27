"""OLED Display driver using I2C."""

import asyncio
import logging
from itertools import cycle
from typing import TYPE_CHECKING

import qrcode
from luma.core.error import DeviceNotFoundError
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import Image, ImageDraw
from PIL.ImageDraw import ImageDraw as ImageDrawType

from boneio.const import OLED_PIN, UPTIME, WHITE
from boneio.core.events import EventBus, async_track_point_in_time, utcnow
from boneio.core.system import HostData
from boneio.core.utils.font_util import make_font
from boneio.core.utils.timeperiod import TimePeriod
from boneio.exceptions import I2CError
from boneio.models import InputState, OutputState

if TYPE_CHECKING:
    from boneio.hardware.i2c.bus import SMBus2I2C

_LOGGER = logging.getLogger(__name__)

# Try to use TTF fonts, fallback to default PIL fonts if not available
try:
    fonts = {
        "big": make_font("DejaVuSans.ttf", 12),
        "small": make_font("DejaVuSans.ttf", 9),
        "extraSmall": make_font("DejaVuSans.ttf", 7),
        "danube": make_font("danube__.ttf", 15, local=True),
    }
except (OSError, IOError):
    # Fallback to default PIL fonts if TTF fonts are not available
    from PIL import ImageFont
    _LOGGER.warning("TTF fonts not found, using default PIL fonts")
    fonts = {
        "big": ImageFont.load_default(),
        "small": ImageFont.load_default(),
        "extraSmall": ImageFont.load_default(),
        "danube": ImageFont.load_default(),
    }

# Screen layout constants
START_ROW = 17
UPTIME_ROWS = list(range(22, 60, 10))
OUTPUT_ROWS = list(range(14, 60, 6))
INPUT_ROWS = list(range(12, 60, 6))
OUTPUT_COLS = range(0, 113, 56)
INPUT_COLS = range(0, 113, 30)


def shorten_name(name: str) -> str:
    """Shorten name for display."""
    if len(name) > 6:
        return f"{name[:4]}{name[-2:]}"
    return name


class Oled:
    """OLED Display driver for SH1106 I2C display."""

    def __init__(
        self,
        host_data: HostData,
        grouped_outputs_by_expander: list[str],
        sleep_timeout: TimePeriod,
        screen_order: list[str],
        input_groups: list[str],
        event_bus: EventBus,
        i2c_bus: "SMBus2I2C | None" = None,
    ):
        """Initialize OLED display.
        
        Args:
            host_data: Host system data
            grouped_outputs_by_expander: List of grouped output names
            sleep_timeout: Sleep timeout period
            screen_order: Configured screen order (placeholders already replaced)
            input_groups: List of input group names
            event_bus: Event bus for handling events
            i2c_bus: I2C bus instance (optional, will create if not provided)
        """
        self._host_data: HostData = host_data
        self._grouped_outputs_by_expander = grouped_outputs_by_expander
        self._event_bus = event_bus
        
        # Screen order is already configured by DisplayManager
        self._screen_order = screen_order
        self._input_groups = input_groups
        _LOGGER.debug("OLED initialized with screen order: %s", self._screen_order)
        
        self._current_screen = self._screen_order[0] if self._screen_order else UPTIME
        self._screen_cycle = cycle(self._screen_order) if self._screen_order else cycle([UPTIME])
        # Skip the first element so that next() shows the second screen on first click
        next(self._screen_cycle)
        self._sleep = False
        self._cancel_sleep_handle = None
        self._sleep_timeout = sleep_timeout
        
        # Initialize I2C display
        try:
            # Use luma.oled for now, but could be refactored to use SMBus2I2C
            serial = i2c(port=2, address=0x3C)
            self._device = sh1106(serial)
            _LOGGER.debug("OLED display initialized successfully")
        except DeviceNotFoundError as err:
            raise I2CError(f"OLED display not found: {err}")
        
        # Subscribe to OLED button events
        self._event_bus.add_event_listener(
            event_type="input",
            entity_id="oled_button",
            listener_id="oled_button_handler",
            target=self._handle_button_press,
        )
    
    async def _output_callback(self, event: OutputState) -> None:
        """Callback for output events."""
        if self._grouped_outputs_by_expander and self._current_screen in self._grouped_outputs_by_expander:
            self._update_display()

    async def _standard_callback(self, event: dict) -> None:
        """Callback for standard events."""
        self._update_display()

    async def _input_callback(self, event: InputState) -> None:
        """Callback for input events."""
        if self._input_groups and self._current_screen in self._input_groups:
            self._update_display()

    def _draw_output(self, data: dict, draw: ImageDrawType) -> None:
        """Draw outputs of GPIO/MCP relays."""
        cols = cycle(OUTPUT_COLS)
        draw.text(
            (1, 1),
            f"Relay {self._current_screen}",
            font=fonts["small"],
            fill=WHITE,
        )
        i = 0
        j = next(cols)
        for k in data.values():
            if len(OUTPUT_ROWS) == i:
                j = next(cols)
                i = 0
            draw.text(
                (j, OUTPUT_ROWS[i]),
                f"{shorten_name(k['name'])} {k['state']}",
                font=fonts["extraSmall"],
                fill=WHITE,
            )
            i += 1

    def _draw_input(self, data: dict, draw: ImageDrawType) -> None:
        """Draw inputs of boneIO Black."""
        cols = cycle(INPUT_COLS)
        draw.text(
            (1, 1),
            f"{self._current_screen}",
            font=fonts["small"],
            fill=WHITE,
        )
        i = 0
        j = next(cols)
        for k in data.values():
            if len(INPUT_ROWS) == i:
                j = next(cols)
                i = 0
            draw.text(
                (j, INPUT_ROWS[i]),
                f"{shorten_name(k['name'])} {k['state']}",
                font=fonts["extraSmall"],
                fill=WHITE,
            )
            i += 1

    def _draw_qr_code(self, url: str) -> None:
        """Draw QR code on the OLED display."""
        if not url:
            return
            
        # Create QR code with box_size 2 and scale down later
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        
        # Create QR code image
        # For mode "1", colors must be int: 0=black, 1=white
        qr_image = qr.make_image(fill_color="white", back_color="black", mode="1")
        qr_image = qr_image.convert("1") # type: ignore
        
        # Create a blank image with OLED dimensions
        display_image = Image.new("1", (128, 64), 0)  # Mode 1, size 128x64, black background
        draw = ImageDraw.Draw(display_image)
        
        # Add title text on the left side
        draw.text((2, 2), "Scan to", font=fonts["small"], fill=WHITE)
        draw.text((2, 12), "access", font=fonts["small"], fill=WHITE)
        draw.text((2, 22), "webui", font=fonts["small"], fill=WHITE)
        
        # Calculate position to align QR code to right and center vertically
        qr_size = qr_image.size if hasattr(qr_image, 'size') else (32, 32)  # Default size  # type: ignore
        x = 128 - qr_size[0] - 2  # Align to right with 2 pixels padding
        y = ((64 - qr_size[1]) // 2)  # Center vertically
        
        # Paste QR code onto center of display image
        # Use bounding box format: (left, top, right, bottom)
        try:
            display_image.paste(qr_image, (x, y, x + qr_size[0], y + qr_size[1]))  # type: ignore
        except Exception as e:
            _LOGGER.error(f"Failed to paste QR code: {e}")
            return
        
        # Display the centered QR code
        self._device.display(display_image)

    async def _handle_button_press(self, event: dict) -> None:
        """Handle button press event from input."""
        _LOGGER.debug(f"OLED button pressed event received: {event}")
        if self._sleep:
            # Display is sleeping - wake it up
            self.wake_up()
        else:
            # Display is active - go to next screen
            self._next_screen()

    def _next_screen(self) -> None:
        """Switch to next screen."""
        # Remove old listeners before switching screen (only if exists)
        try:
            self._event_bus.remove_event_listener(listener_id=f"oled_{self._current_screen}")
        except KeyError:
            # Listener doesn't exist yet, skip removal
            pass
        self._current_screen = next(self._screen_cycle)
        self.render_display()

    def render_display(self) -> None:
        """Render display - main method that decides what to display."""
        
        data = self._host_data.get(self._current_screen)
        if data:
            if self._current_screen == "web":
                self._draw_qr_code(url=str(data))
            elif isinstance(data, dict):
                with canvas(self._device) as draw:
                    if (
                        self._grouped_outputs_by_expander
                        and self._current_screen in self._grouped_outputs_by_expander
                    ):
                        self._draw_output(data, draw)
                        for id in data.keys():
                            self._event_bus.add_event_listener(
                                event_type="output", 
                                entity_id=id, 
                                listener_id=f"oled_{self._current_screen}", 
                                target=self._output_callback
                            )
                    elif self._current_screen == UPTIME:
                        self._draw_uptime(draw)
                        self._event_bus.add_event_listener(
                            event_type="host", 
                            entity_id=f"{self._current_screen}_hoststats", 
                            listener_id=f"oled_{self._current_screen}", 
                            target=self._standard_callback
                        )
                    elif self._input_groups and self._current_screen in self._input_groups:
                        self._draw_input(data, draw)
                        for id in data.keys():
                            self._event_bus.add_event_listener(
                                event_type="input", 
                                entity_id=id, 
                                listener_id=f"oled_{self._current_screen}", 
                                target=self._input_callback
                            )
                    else:
                        self._draw_standard(data, draw)
                        self._event_bus.add_event_listener(
                            event_type="host", 
                            entity_id=f"{self._current_screen}_hoststats", 
                            listener_id=f"oled_{self._current_screen}", 
                            target=self._standard_callback
                        )
        else:
            self._next_screen()
        
        if not self._cancel_sleep_handle and self._sleep_timeout.total_seconds > 0:
            self.start_sleep_timer()

    def _update_display(self) -> None:
        """Update OLED display without re-registering listeners."""
        if self._sleep:
            return
        
        try:
            data = self._host_data.get(self._current_screen)
            if not data:
                return
            
            if self._current_screen == "web":
                self._draw_qr_code(url=str(data))
            elif isinstance(data, dict):
                with canvas(self._device) as draw:
                    if (
                        self._grouped_outputs_by_expander
                        and self._current_screen in self._grouped_outputs_by_expander
                    ):
                        self._draw_output(data, draw)
                    elif self._current_screen == UPTIME:
                        self._draw_uptime(draw)
                    elif self._input_groups and self._current_screen in self._input_groups:
                        self._draw_input(data, draw)
                    else:
                        self._draw_standard(data, draw)
        except Exception as e:
            _LOGGER.error(f"Failed to update OLED display: {e}")

    def _draw_standard(self, data: dict, draw: ImageDrawType) -> None:
        """Draw standard information about host screen."""
        draw.text(
            (1, 1),
            self._current_screen.replace("_", " ").capitalize(),
            font=fonts["big"],
            fill=WHITE,
        )
        row_no = START_ROW
        for k in data:
            draw.text(
                (3, row_no),
                f"{k} {data[k]}",
                font=fonts["small"],
                fill=WHITE,
            )
            row_no += 15

    def _draw_uptime(self, draw: ImageDrawType) -> None:
        """Draw uptime screen with boneIO logo."""
        uptime_data = self._host_data.get(UPTIME)
        
        if not isinstance(uptime_data, dict):
            # Fallback for simple string data
            draw.text((1, 1), "Uptime", font=fonts["big"], fill=WHITE)
            draw.text((3, START_ROW), str(uptime_data), font=fonts["small"], fill=WHITE)
            return
        
        # Draw boneIO logo at the top (split into two parts)
        draw.text((3, 3), "bone", font=fonts["danube"], fill=WHITE)
        draw.text((53, 3), "iO", font=fonts["danube"], fill=WHITE)
        
        # Check if data follows the format with position info
        if all(isinstance(v, dict) and 'data' in v for v in uptime_data.values()):
            for k in uptime_data:
                text = uptime_data[k]["data"]
                font_size_key = uptime_data[k]["fontSize"]
                font_to_use = fonts.get(font_size_key, fonts["small"])
                col = uptime_data[k]["col"]
                row = uptime_data[k]["row"]
                
                # Use UPTIME_ROWS for Y positioning
                y_position = UPTIME_ROWS[row] if row < len(UPTIME_ROWS) else 22 + row * 10
                
                # Display as "key: value" format
                draw.text(
                    (col, y_position),
                    f"{k}: {text}",
                    font=font_to_use,
                    fill=WHITE,
                )
        else:
            # Old format - simple key-value pairs
            row_no = START_ROW
            for key, value in uptime_data.items():
                draw.text(
                    (3, row_no),
                    f"{key}: {value}",
                    font=fonts["small"],
                    fill=WHITE,
                )
                row_no += 15

    def start_sleep_timer(self) -> None:
        """Start sleep timer."""
        if self._cancel_sleep_handle:
            self._cancel_sleep_handle()
        
        self._cancel_sleep_handle = async_track_point_in_time(
            loop=asyncio.get_running_loop(),
            job=self._sleep_callback,
            point_in_time=utcnow() + self._sleep_timeout.as_timedelta,
        )

    async def _sleep_callback(self, timestamp) -> None:
        """Sleep callback."""
        self._sleep = True
        self._cancel_sleep_handle = None
        with canvas(self._device) as draw:
            draw.rectangle(
                self._device.bounding_box, outline="black", fill="black"
            )
        _LOGGER.debug("OLED display sleeping")

    def wake_up(self) -> None:
        """Wake up display."""
        self._sleep = False
        if self._cancel_sleep_handle:
            self._cancel_sleep_handle()
            self._cancel_sleep_handle = None
        self._update_display()

    def shutdown(self) -> None:
        """Shutdown OLED display."""
        if self._cancel_sleep_handle:
            self._cancel_sleep_handle()
        # Clear display
        try:
            with canvas(self._device) as draw:
                draw.rectangle([0, 0, 127, 63], outline=0, fill=0)
        except Exception as e:
            _LOGGER.error(f"Failed to shutdown OLED display: {e}")
