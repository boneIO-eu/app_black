"""PCA9685 PWM module."""

from __future__ import annotations
import asyncio
import logging
from typing import Callable
from adafruit_pca9685 import PCA9685, PCAChannels

from boneio.helper.events import async_track_point_in_time, utcnow
from boneio.helper.util import callback

from boneio.const import LED, NONE, OFF, ON, STATE, SWITCH, BRIGHTNESS, RELAY
from boneio.helper import BasicMqtt

_LOGGER = logging.getLogger(__name__)


class PWMPCA(BasicMqtt):
    """Initialize PWMPCA."""

    def __init__(
        self,
        pin: int,
        pca: PCA9685,
        percentage_default_brightness: int,
        callback: Callable,
        id: str | None = None,
        output_type=SWITCH,
        restored_state: bool = False,
        restored_brightness: int = 0,
        **kwargs,
    ) -> None:
        """Initialize PWMPCA."""
        self._pin: PCAChannels = pca.channels[pin]

        self._momentary_turn_on = kwargs.pop("momentary_turn_on", None)
        self._momentary_turn_off = kwargs.pop("momentary_turn_off", None)
        super().__init__(id=id, name=id, topic_type=RELAY, **kwargs)

        self._output_type = output_type
        self._percentage_default_brightness = percentage_default_brightness

        if output_type == NONE:
            self._momentary_turn_on = None
            self._momentary_turn_off = None

        if restored_state:
            self._state = ON
            self._brightness = restored_brightness
        else:
            self._state = OFF
            self._brightness = 0

        self._callback = callback
        self._loop = asyncio.get_running_loop()

        self._pin_id = pin
        _LOGGER.debug("Setup PCA with pin %s", self._pin_id)

    @property
    def is_pca_type(self) -> bool:
        """Check if relay is pca type."""
        return True

    @property
    def output_type(self) -> str:
        """HA type."""
        return self._output_type

    @property
    def is_led(self) -> bool:
        """Check if HA type is light"""
        return self._output_type == LED

    @property
    def id(self) -> str:
        """Id of the relay.
        Has to be trimmed out of spaces because of MQTT handling in HA."""
        return self._id

    @property
    def name(self) -> str:
        """Not trimmed name."""
        return self._name

    @property
    def state(self) -> str:
        """Is relay active."""
        return self._state

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

        if self._momentary_turn_on:
            async_track_point_in_time(
                loop=self._loop,
                action=lambda x: self._momentary_callback(time=x, action=self.turn_off),
                point_in_time=utcnow() + self._momentary_turn_on.as_timedelta,
            )
        self._loop.call_soon_threadsafe(self.send_state)

    def turn_off(self) -> None:
        """Call turn off action."""
        _LOGGER.debug("Turn off relay.")
        self._pin.duty_cycle = 0
        if self._momentary_turn_off:
            async_track_point_in_time(
                loop=self._loop,
                action=lambda x: self._momentary_callback(time=x, action=self.turn_on),
                point_in_time=utcnow() + self._momentary_turn_off.as_timedelta,
            )
        self._loop.call_soon_threadsafe(self.send_state)

    @callback
    def _momentary_callback(self, time, action):
        _LOGGER.info("Momentary callback at %s", time)
        action()

    def send_state(self) -> None:
        """Send state to Mqtt on action."""
        state = ON if self.is_active else OFF
        if self.output_type != NONE:
            self._send_message(
                topic=self._send_topic,
                payload={BRIGHTNESS: self.brightness, STATE: state},
            )
        self._loop.call_soon_threadsafe(self._callback)
