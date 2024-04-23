"""PCA9685 PWM module."""

from __future__ import annotations
import logging
from adafruit_pca9685 import PCA9685, PCAChannels

from boneio.const import LED, OFF, ON, STATE, SWITCH, BRIGHTNESS, PCA
from boneio.relay.basic import BasicRelay

_LOGGER = logging.getLogger(__name__)


class PWMPCA(BasicRelay):
    """Initialize PWMPCA."""

    def __init__(
        self,
        pin: int,
        pca: PCA9685,
        percentage_default_brightness: int,
        output_type=SWITCH,
        restored_state: bool = False,
        restored_brightness: int = 0,
        **kwargs,
    ) -> None:
        """Initialize PWMPCA."""
        self._pin: PCAChannels = pca.channels[pin]
        super().__init__(
            **kwargs, output_type=output_type, restored_state=restored_state
        )
        self._percentage_default_brightness = percentage_default_brightness
        self._brightness = restored_brightness if restored_state else 0
        self._pin_id = pin
        _LOGGER.debug("Setup PCA with pin %s", self._pin_id)

    @property
    def expander_type(self) -> str:
        """Check expander type."""
        return PCA

    @property
    def is_led(self) -> bool:
        """Check if HA type is light"""
        return self._output_type == LED

    @property
    def brightness(self) -> int:
        """Get brightness in 0-65535 scale. PCA can force over 65535 value after restart, so we treat that as a 0"""
        try:
            if self._pin.duty_cycle > 65535:
                return 0
            return self._pin.duty_cycle
        except:
            _LOGGER.error("Cant read value form driver on pin %s", self._pin_id)
            return 0

    def set_brightness(self, value: int):
        try:
            """Set brightness in 0-65535 vale"""
            _LOGGER.debug("Set brightness relay %s.", value)
            self._pin.duty_cycle = value
        except:
            _LOGGER.error("Cant set value form driver on pin %s", self._pin_id)

    @property
    def is_active(self) -> bool:
        """Is relay active."""
        return self.brightness > 1

    def turn_on(self) -> None:
        """Call turn on action. When brightness is 0, and turn on by switch, default set value to 1%"""
        _LOGGER.debug("Turn on relay.")
        if self.brightness == 0:
            self.set_brightness(int(65535 / 100 * self._percentage_default_brightness))
        self._execute_momentary_turn(momentary_type=ON)
        self._loop.call_soon_threadsafe(self.send_state)
        self._loop.call_soon_threadsafe(self._callback)

    def turn_off(self) -> None:
        """Call turn off action."""
        _LOGGER.debug("Turn off relay.")
        self._pin.duty_cycle = 0
        self._execute_momentary_turn(momentary_type=OFF)
        self._loop.call_soon_threadsafe(self.send_state)
        self._loop.call_soon_threadsafe(self._callback)

    def payload(self) -> dict:
        return {BRIGHTNESS: self.brightness, STATE: self.state}
