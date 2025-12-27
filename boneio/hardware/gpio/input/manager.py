"""GPIO Manager using libgpiod for BeagleBone GPIO control."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Dict, Tuple

import gpiod
from gpiod import LineSettings
from gpiod.line import Bias, Direction, Edge

from boneio.const import PINS

if TYPE_CHECKING:
    from boneio.components.input.detectors import MultiClickDetector, BinarySensorDetector

_LOGGER = logging.getLogger(__name__)


@dataclass
class GpioInputDefinition:
    """Definition of a GPIO input."""
    name: str
    pin: str
    chip: int
    line: int
    bias: Bias
    detector: "MultiClickDetector | BinarySensorDetector"  # Type hints for detectors


class GpioManager:
    """Centralized GPIO manager using libgpiod."""

    # BeagleBone Black hardware limit for debounce via gpiod
    MAX_DEBOUNCE_MS = 7

    def __init__(self, loop: asyncio.AbstractEventLoop, debounce_ms: int = 7):
        """Initialize GPIO manager.
        
        Args:
            loop: Asyncio event loop
            debounce_ms: Debounce time in milliseconds (max 7ms for BeagleBone hardware)
        
        Raises:
            ValueError: If debounce_ms exceeds hardware limit
        """
        if debounce_ms > self.MAX_DEBOUNCE_MS:
            raise ValueError(
                f"debounce_ms={debounce_ms} exceeds BeagleBone hardware limit "
                f"of {self.MAX_DEBOUNCE_MS}ms"
            )
        self._loop = loop
        self._debounce_ms = debounce_ms
        self._inputs: list[GpioInputDefinition] = []
        self._requests: Dict[int, gpiod.LineRequest] = {}
        self._file_descriptors: list[int] = []
        self._aliases: Dict[Tuple[int, int], str] = {}
        self._detectors: Dict[Tuple[int, int], "MultiClickDetector | BinarySensorDetector"] = {}
        self._running = False

    async def _cleanup_stale_requests(self) -> None:
        """Try to cleanup any stale GPIO line requests."""
        # This is a safety measure - if previous process crashed
        # Note: gpiod doesn't provide a direct way to force-release lines
        # The best we can do is wait a bit and let the kernel clean up
        await asyncio.sleep(0.1)
    
    def add_input(
        self,
        name: str,
        pin: str,
        detector: "MultiClickDetector | BinarySensorDetector",
        gpio_mode: str = "gpio"
    ) -> None:
        """Add a GPIO input to monitor.
        
        Args:
            name: Name of the input
            pin: Pin name (e.g., "P8_30")
            detector: Detector instance (MultiClickDetector or BinarySensorDetector)
            gpio_mode: GPIO mode (gpio, gpio_pu, gpio_pd)
        """
        if pin not in PINS:
            _LOGGER.error("Pin %s not found in PINS mapping", pin)
            return

        pin_info = PINS[pin]
        chip = pin_info["chip"]
        line = pin_info["line"]
        key = (chip, line)
        
        # Check if pin is already registered
        if key in self._detectors:
            if self._running:
                # During runtime, just update the detector (for reload scenarios)
                _LOGGER.info("Pin %s already registered, updating detector", pin)
                self._detectors[key] = detector
                self._aliases[key] = f"{name} ({pin})"
                return
            else:
                _LOGGER.warning("Pin %s already registered during init, skipping", pin)
                return

        # Cannot add new GPIO lines while manager is running (gpiod limitation)
        if self._running:
            _LOGGER.error(
                "Cannot add new GPIO pin %s while manager is running. "
                "This pin was not configured at startup.",
                pin
            )
            return

        # Map gpio_mode to gpiod.Bias
        bias_map = {
            "gpio": Bias.AS_IS,
            "gpio_pu": Bias.AS_IS,
            "gpio_pd": Bias.PULL_DOWN,
            "gpio_input": Bias.AS_IS,
        }
        bias = bias_map.get(gpio_mode, Bias.AS_IS)

        input_def = GpioInputDefinition(
            name=name,
            pin=pin,
            chip=chip,
            line=line,
            bias=bias,
            detector=detector,
        )
        self._inputs.append(input_def)
        
        # Store detector for later use
        self._detectors[key] = detector
        self._aliases[key] = f"{name} ({pin})"
        
        _LOGGER.debug(
            "Registered input %s on pin %s (chip%d, line%d) with mode %s",
            name, pin, chip, line, gpio_mode
        )

    async def _start_debug_mode(
        self, 
        chip: int, 
        chip_definitions: list[GpioInputDefinition],
        config: Dict[Tuple[int, ...], LineSettings],
        consumer: str
    ) -> tuple[Dict[Tuple[int, ...], LineSettings], list[tuple[int, str]]]:
        """Debug mode: Test each line individually to identify problematic ones.
        
        Returns:
            Tuple of (successful_lines, failed_lines)
        """
        successful_lines = {}
        failed_lines = []
        
        _LOGGER.info("🔍 DEBUG MODE: Testing lines individually on chip %d", chip)
        
        for line_tuple, settings in config.items():
            line_num = line_tuple[0]
            # Find the input name for this line
            input_name = "unknown"
            for inp in chip_definitions:
                if inp.line == line_num:
                    input_name = f"{inp.name} ({inp.pin})"
                    break
            
            _LOGGER.info("  Testing line %d (%s)...", line_num, input_name)
            
            # Try to request this single line
            single_config = {line_tuple: settings}
            try:
                test_request = gpiod.request_lines(
                    f"/dev/gpiochip{chip}", 
                    consumer=f"{consumer}-test-line{line_num}", 
                    config=single_config  # type: ignore[arg-type]
                )
                # Success! Release immediately and add to successful list
                test_request.release()
                successful_lines[line_tuple] = settings
                _LOGGER.info("    ✓ Line %d (%s) is available", line_num, input_name)
            except OSError as err:
                if err.errno == 16:
                    _LOGGER.error("    ✗ Line %d (%s) is BUSY!", line_num, input_name)
                    failed_lines.append((line_num, input_name))
                else:
                    _LOGGER.error("    ✗ Line %d (%s) error: %s", line_num, input_name, err)
                    failed_lines.append((line_num, input_name))
            except ValueError as err:
                _LOGGER.error("    ✗ Line %d (%s) invalid config: %s", line_num, input_name, err)
                failed_lines.append((line_num, input_name))
        
        return successful_lines, failed_lines

    async def start(self, debug_mode: bool = False) -> None:
        """Start monitoring GPIO inputs.
        
        Args:
            debug_mode: If True, test each line individually to identify issues (slower).
                       If False, request all lines at once (faster, production mode).
        """
        if self._running:
            _LOGGER.warning("GPIO manager already running")
            return

        if not self._inputs:
            _LOGGER.warning("No GPIO inputs registered")
            return
        
        _LOGGER.info("Starting GPIO manager with %d inputs", len(self._inputs))
        for inp in self._inputs:
            _LOGGER.debug("  Input: %s (chip%d/line%d)", inp.name, inp.chip, inp.line)
        
        # Try to clean up any stale line requests first
        await self._cleanup_stale_requests()

        # Group inputs by chip
        grouped_inputs: Dict[int, list[GpioInputDefinition]] = defaultdict(list)
        for input_def in self._inputs:
            grouped_inputs[input_def.chip].append(input_def)

        # Create line requests for each chip
        for chip, chip_definitions in grouped_inputs.items():
            config: Dict[Tuple[int, ...], LineSettings] = {}
            alias_map: Dict[Tuple[int, int], str] = {}
            
            for definition in chip_definitions:
                settings_kwargs = {
                    "direction": Direction.INPUT,
                    "edge_detection": Edge.BOTH,
                    "bias": definition.bias,
                }
                # Note: BeagleBone hardware debounce can cause issues with Edge.BOTH
                # Use software debounce in detectors instead
                # if self._debounce_ms > 0 and self._debounce_ms <= self.MAX_DEBOUNCE_MS:
                #     settings_kwargs["debounce_period"] = timedelta(
                #         milliseconds=self._debounce_ms
                #     )

                config[(definition.line,)] = LineSettings(**settings_kwargs)
                alias = f"{definition.name} ({definition.pin})"
                key = (chip, definition.line)
                alias_map[key] = alias

            consumer = f"boneio-chip{chip}"
            _LOGGER.info("Configuring chip %d with %d lines", chip, len(config))
            
            if debug_mode:
                # Debug mode: Test each line individually
                successful_lines, failed_lines = await self._start_debug_mode(
                    chip, chip_definitions, config, consumer
                )
                
                # If any lines failed, report and skip this chip
                if failed_lines:
                    _LOGGER.error(
                        "Chip %d: %d/%d lines failed. Failed lines: %s",
                        chip, len(failed_lines), len(config), 
                        [f"{line}({name})" for line, name in failed_lines]
                    )
                    _LOGGER.error("Skipping chip %d due to busy/invalid lines", chip)
                    continue
                
                config = successful_lines
                _LOGGER.info("All lines on chip %d tested OK, requesting together...", chip)
            
            # Request all lines at once (fast mode or after debug validation)
            try:
                request = gpiod.request_lines(
                    f"/dev/gpiochip{chip}", consumer=consumer, config=config  # type: ignore[arg-type]
                )
                self._requests[chip] = request
                _LOGGER.info("✓ Successfully configured chip %d with %d lines", chip, len(config))
            except OSError as err:
                if err.errno == 16:
                    _LOGGER.error(
                        "GPIO chip %d lines are BUSY (attempted: %s). "
                        "Another boneio process may still be running. Check: sudo cat /sys/kernel/debug/gpio",
                        chip, list(config.keys())
                    )
                    if not debug_mode:
                        _LOGGER.info("💡 Tip: Restart with debug_mode=True to identify which specific line is busy")
                _LOGGER.error("Failed to request lines on chip %d: %s", chip, err)
                continue

            summary = ", ".join(
                f"{alias} (line {line})" for (_, line), alias in alias_map.items()
            )
            _LOGGER.info("Monitoring /dev/gpiochip%s on: %s", chip, summary)

        # Register readers in asyncio loop
        for chip, request in self._requests.items():
            fd = request.fileno()
            self._file_descriptors.append(fd)
            self._loop.add_reader(fd, self._handle_gpiod_events, chip, request)

        self._running = True
        _LOGGER.info("GPIO manager started monitoring %d inputs", len(self._inputs))

    def _handle_gpiod_events(self, chip: int, request: gpiod.LineRequest) -> None:
        """Handle GPIO events from libgpiod.
        
        Args:
            chip: GPIO chip number
            request: Line request object
        """
        for event in request.read_edge_events():
            line = event.line_offset
            key = (chip, line)
            
            if key in self._detectors:
                detector = self._detectors[key]
                alias = self._aliases.get(key, f"chip{chip}/line{line}")
                
                _LOGGER.debug(
                    "GPIO event: %s edge on %s",
                    "rising" if event.event_type == event.Type.RISING_EDGE else "falling",
                    alias,
                )
                
                # Call the detector's handle_event method
                try:
                    detector.handle_event(event)
                except Exception as exc:
                    _LOGGER.error(
                        "Error in GPIO detector for %s: %s",
                        alias,
                        exc,
                        exc_info=True,
                    )

    def read_value(self, pin: str) -> bool:
        """Read current value of a GPIO pin.
        
        Args:
            pin: Pin name (e.g., "P8_30")
            
        Returns:
            True if pin is high, False if low
        """
        if pin not in PINS:
            _LOGGER.error("Pin %s not found in PINS mapping", pin)
            return False

        pin_info = PINS[pin]
        chip = pin_info["chip"]
        line = pin_info["line"]

        if chip not in self._requests:
            _LOGGER.error("Chip %d not initialized", chip)
            return False

        request = self._requests[chip]
        values = request.get_values([line])
        # get_values returns a list with one element (index 0) for the requested line
        return bool(values[0])

    def is_pin_registered(self, pin: str) -> bool:
        """Check if a pin is registered with the GPIO manager.
        
        Args:
            pin: Pin name to check
            
        Returns:
            True if pin is registered, False otherwise
        """
        if pin not in PINS:
            return False
            
        pin_info = PINS[pin]
        key = (pin_info["chip"], pin_info["line"])
        return key in self._detectors

    async def stop(self) -> None:
        """Stop monitoring GPIO inputs and cleanup resources."""
        if not self._running:
            return

        _LOGGER.info("Stopping GPIO manager...")

        # Remove readers from event loop
        for fd in self._file_descriptors:
            self._loop.remove_reader(fd)

        # Release line requests
        for request in self._requests.values():
            request.release()

        self._file_descriptors.clear()
        self._requests.clear()
        self._running = False
        
        _LOGGER.info("GPIO manager stopped")


# Global GPIO manager instance
_gpio_manager: GpioManager | None = None


def get_gpio_manager(
    loop: asyncio.AbstractEventLoop | None = None,
    debounce_ms: int = 7
) -> GpioManager:
    """Get or create the global GPIO manager instance.
    
    Args:
        loop: Asyncio event loop (required on first call)
        debounce_ms: Debounce time in milliseconds
        
    Returns:
        Global GPIO manager instance
    """
    global _gpio_manager
    
    if _gpio_manager is None:
        if loop is None:
            raise ValueError("Event loop required to create GPIO manager")
        _gpio_manager = GpioManager(loop, debounce_ms)
    
    return _gpio_manager
