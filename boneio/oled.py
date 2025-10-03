import asyncio
import logging
from itertools import cycle
from typing import List

import qrcode
from luma.core.error import DeviceNotFoundError
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import Image, ImageDraw

from boneio.const import OLED_PIN, UPTIME, WHITE
from boneio.helper import (
    HostData,
    I2CError,
    TimePeriod,
    edge_detect,
    make_font,
    setup_input,
)
from boneio.helper.events import EventBus, async_track_point_in_time, utcnow
from boneio.models import InputState, OutputState, SensorState

_LOGGER = logging.getLogger(__name__)

fonts = {
    "big": make_font("DejaVuSans.ttf", 12),
    "small": make_font("DejaVuSans.ttf", 9),
    "extraSmall": make_font("DejaVuSans.ttf", 7),
    "danube": make_font("danube__.ttf", 15, local=True),
}

# screen_order = [UPTIME, NETWORK, CPU, DISK, MEMORY, SWAP]

# STANDARD_ROWS = [17, 32, 47]
START_ROW = 17
UPTIME_ROWS = list(range(22, 60, 10))
OUTPUT_ROWS = list(range(14, 60, 6))
INPUT_ROWS = list(range(12, 60, 6))
OUTPUT_COLS = range(0, 113, 56)
INPUT_COLS = range(0, 113, 30)


def shorten_name(name: str) -> str:
    if len(name) > 6:
        return f"{name[:4]}{name[-2:]}"
    return name


class Oled:
    """Oled display class."""

    def __init__(
        self,
        host_data: HostData,
        grouped_outputs_by_expander: list[str],
        sleep_timeout: TimePeriod,
        screen_order: list[str],
        event_bus: EventBus
    ) -> None:
        """Initialize OLED screen."""
        self._loop = asyncio.get_running_loop()
        self._event_bus = event_bus
        self.grouped_outputs_by_expander = None
        self._input_groups = []
        self._host_data = host_data

        def configure_outputs() -> None:
            try:
                _ind_screen = screen_order.index("outputs")
                if not grouped_outputs_by_expander:
                    _LOGGER.debug("No outputs configured. Omitting in screen.")
                    return
                screen_order.pop(_ind_screen)
                screen_order[_ind_screen:_ind_screen] = grouped_outputs_by_expander
                self.grouped_outputs_by_expander = grouped_outputs_by_expander
            except ValueError:
                pass

        def configure_inputs() -> None:
            try:
                _inputs_screen = screen_order.index("inputs")
                input_groups = [
                    f"Inputs screen {i + 1}"
                    for i in range(
                        0, self._host_data.inputs_length, 1
                    )  # self._host_data.inputs_length
                ]
                screen_order.pop(_inputs_screen)
                screen_order[_inputs_screen:_inputs_screen] = input_groups
                self._input_groups = input_groups
            except ValueError:
                _LOGGER.debug("No inputs configured. Omitting in screen.")
                pass

        try:
            _ina219_screen = screen_order.index("ina219")
            screen_order.pop(_ina219_screen)
        except ValueError:
            pass

        configure_outputs()
        configure_inputs()
        if not screen_order:
            _LOGGER.warning("No available screens configured. OLED won't be working.")
            self._current_screen = None
            return
        self._screen_order = cycle(screen_order)
        self._current_screen = next(self._screen_order)
        self._host_data = host_data
        self._sleep = False
        self._cancel_sleep_handle = None
        self._sleep_timeout = sleep_timeout
        setup_input(pin=OLED_PIN, pull_mode="gpio_pu")
        edge_detect(pin=OLED_PIN, callback=self._handle_press, bounce=240)
        try:
            serial = i2c(port=2, address=0x3C)
            self._device = sh1106(serial)
        except DeviceNotFoundError as err:
            raise I2CError(err)
        _LOGGER.debug("Configuring OLED screen.")

    def _draw_standard(self, data: dict, draw: ImageDraw) -> None:
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

    def _sleeptime(self):
        with canvas(self._device) as draw:
            draw.rectangle(
                self._device.bounding_box, outline="black", fill="black"
            )
        self._sleep = True
        _LOGGER.debug("OLED is going to sleep.")

    def _draw_uptime(self, data: dict, draw: ImageDraw) -> None:
        """Draw uptime screen with boneIO logo."""
        draw.text((3, 3), "bone", font=fonts["danube"], fill=WHITE)
        draw.text((53, 3), "iO", font=fonts["danube"], fill=WHITE)
        for k in data:
            text = data[k]["data"]
            fontSize = fonts[data[k]["fontSize"]]
            draw.text(
                (data[k]["col"], UPTIME_ROWS[data[k]["row"]]),
                f"{k}: {text}",
                font=fontSize,
                fill=WHITE,
            )

    def _draw_output(self, data: dict, draw: ImageDraw) -> None:
        "Draw outputs of GPIO/MCP relays."
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

    def _draw_input(self, data: dict, draw: ImageDraw) -> None:
        "Draw inputs of boneIO Black."
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

    def render_display(self) -> None:
        """Render display."""
        data = self._host_data.get(self._current_screen)
        if data:
            if self._current_screen == "web":
                self.draw_qr_code(url=data)
            else:
                with canvas(self._device) as draw:
                    if (
                        self.grouped_outputs_by_expander
                        and self._current_screen in self.grouped_outputs_by_expander
                    ):
                        self._draw_output(data, draw)
                        for id in data.keys():
                            self._event_bus.add_event_listener(event_type="output", entity_id=id, listener_id=f"oled_{self._current_screen}", target=self._output_callback)
                    elif self._current_screen == UPTIME:
                        self._draw_uptime(data, draw)
                        self._event_bus.add_event_listener(event_type="host", entity_id=f"{self._current_screen}_hoststats", listener_id=f"oled_{self._current_screen}", target=self._standard_callback)
                    elif (
                        self._input_groups
                        and self._current_screen in self._input_groups
                    ):
                        for id in data.keys():
                            self._event_bus.add_event_listener(event_type="input", entity_id=id, listener_id=f"oled_{self._current_screen}", target=self._input_callback)
                        self._draw_input(data, draw)
                    else:
                        self._draw_standard(data, draw)
                        self._event_bus.add_event_listener(event_type="host", entity_id=f"{self._current_screen}_hoststats", listener_id=f"oled_{self._current_screen}", target=self._standard_callback)
        else:
            self._handle_press(pin=None)
        if not self._cancel_sleep_handle and self._sleep_timeout.total_seconds > 0:
            self._cancel_sleep_handle = async_track_point_in_time(
                loop=self._loop,
                job=lambda x: self._sleeptime(),
                point_in_time=utcnow() + self._sleep_timeout.as_timedelta,
            )

    async def _output_callback(self, event: OutputState):
        if self.grouped_outputs_by_expander and self._current_screen in self.grouped_outputs_by_expander:
            self.handle_data_update(type=self._current_screen)

    async def _standard_callback(self, event: SensorState):
        self.handle_data_update(type=UPTIME)

    async def _input_callback(self, event: InputState):
        self.handle_data_update(type="inputs")

    def handle_data_update(self, type: str):
        """Callback to handle new data present into screen."""
        if not self._current_screen:
            return
        if (
            type == "inputs"
            and self._current_screen in self._input_groups
            or type == self._current_screen
        ) and not self._sleep:
            self.render_display()

    def _handle_press(self, pin: any) -> None:
        """Handle press of PIN for OLED display."""
        if self._cancel_sleep_handle:
            self._cancel_sleep_handle()
            self._cancel_sleep_handle = None
        if not self._sleep:
            self._event_bus.remove_event_listener(listener_id=f"oled_{self._current_screen}")
            self._current_screen = next(self._screen_order)
        else:
            self._sleep = False
        self.render_display()

    def draw_qr_code(self, url: str):
        """Draw QR code on the OLED display."""
        if not url:
            return
            
        # Create QR code with box_size 2 and scale down later
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        
        # Create QR code image
        qr_image = qr.make_image(fill_color=WHITE, back_color="black")
        qr_image = qr_image.convert("1")  # Convert to binary mode
        
        # Scale the QR code down to 0.8 of its size
        # Create a blank image with OLED dimensions
        display_image = Image.new("1", (128, 64), 0)  # Mode 1, size 128x64, black background
        draw = ImageDraw.Draw(display_image)
        
        # Add title text on the left side
        # text_width = fonts["small"].getsize(title)[0]
        draw.text((2, 2), "Scan to", font=fonts["small"], fill=WHITE)
        draw.text((2, 12), "access", font=fonts["small"], fill=WHITE)
        draw.text((2, 22), "webui", font=fonts["small"], fill=WHITE)
        
        # Calculate position to align QR code to right and center vertically
        x = 128 - qr_image.size[0] - 2  # Align to right with 2 pixels padding
        y = ((64 - qr_image.size[1]) // 2)  # Center vertically
        
        # Paste QR code onto center of display image
        display_image.paste(qr_image, (x, y))
        
        # Display the centered QR code
        self._device.display(display_image)
