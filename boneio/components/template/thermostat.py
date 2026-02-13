"""BoneIO Thermostat — bang-bang climate controller.

Reads temperature from any boneIO sensor (I2C, Dallas, Modbus, ADC) and
controls an output (relay) to maintain the target temperature using
hysteresis-based on/off control.

Exposed to Home Assistant as ``climate`` entity via MQTT autodiscovery.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from boneio.const import CLIMATE, ON, OFF, SENSOR, STATE

if TYPE_CHECKING:
    from boneio.core.messaging.basic import MessageBus
    from boneio.core.events.bus import EventBus
    from boneio.components.output.basic import BasicOutput

_LOGGER = logging.getLogger(__name__)

# HA climate modes
MODE_OFF = "off"
MODE_HEAT = "heat"

# HA climate actions
ACTION_OFF = "off"
ACTION_IDLE = "idle"
ACTION_HEATING = "heating"


class BoneIOThermostat:
    """Bang-bang thermostat that controls an output based on temperature.

    Args:
        id: Unique thermostat identifier.
        name: Human-readable name for HA.
        sensor_id: ID of the temperature sensor to read.
        output: The output (relay) to control.
        message_bus: MessageBus for MQTT communication.
        event_bus: EventBus for internal events.
        topic_prefix: MQTT topic prefix.
        mode: Initial climate mode ('heat' or 'off').
        target_temperature: Initial target temperature in °C.
        hysteresis: Temperature hysteresis in °C (default 0.5).
        min_temperature: Minimum settable temperature (default 5).
        max_temperature: Maximum settable temperature (default 35).
        area: Optional area ID for HA sub-device.
    """

    def __init__(
        self,
        id: str,
        name: str,
        sensor_id: str,
        output: "BasicOutput",
        message_bus: "MessageBus",
        event_bus: "EventBus",
        topic_prefix: str,
        mode: str = MODE_HEAT,
        target_temperature: float = 21.0,
        hysteresis: float = 0.5,
        min_temperature: float = 5.0,
        max_temperature: float = 35.0,
        area: str | None = None,
    ) -> None:
        self._id = id
        self._name = name
        self._sensor_id = sensor_id
        self._output = output
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._topic_prefix = topic_prefix
        self._area = area

        # Climate state
        self._mode = mode if mode in (MODE_OFF, MODE_HEAT) else MODE_HEAT
        self._target_temperature = target_temperature
        self._hysteresis = hysteresis
        self._min_temperature = min_temperature
        self._max_temperature = max_temperature
        self._current_temperature: float | None = None
        self._action = ACTION_IDLE if self._mode == MODE_HEAT else ACTION_OFF

        # MQTT topics
        self._state_topic = f"{topic_prefix}/{CLIMATE}/{id}"
        self._cmd_mode_topic = f"{topic_prefix}/cmd/{CLIMATE}/{id}/mode/set"
        self._cmd_temp_topic = f"{topic_prefix}/cmd/{CLIMATE}/{id}/temperature/set"

        # Periodic evaluation task
        self._eval_task: asyncio.Task | None = None

        _LOGGER.info(
            "Initialized BoneIOThermostat: id=%s, sensor=%s, output=%s, "
            "target=%.1f°C, hysteresis=%.1f°C",
            id, sensor_id, output.id, target_temperature, hysteresis,
        )

    # -- Properties ----------------------------------------------------------

    @property
    def id(self) -> str:
        """Get thermostat ID."""
        return self._id

    @property
    def name(self) -> str:
        """Get thermostat name."""
        return self._name

    @property
    def area(self) -> str | None:
        """Get area ID."""
        return self._area

    @property
    def mode(self) -> str:
        """Get current climate mode."""
        return self._mode

    @property
    def action(self) -> str:
        """Get current climate action."""
        return self._action

    @property
    def target_temperature(self) -> float:
        """Get target temperature."""
        return self._target_temperature

    @property
    def current_temperature(self) -> float | None:
        """Get last known current temperature."""
        return self._current_temperature

    # -- MQTT command handlers -----------------------------------------------

    async def handle_mode_command(self, _topic: str, payload: str) -> None:
        """Handle mode command from HA (off / heat).

        Args:
            _topic: MQTT topic (unused).
            payload: New mode string.
        """
        mode = payload.strip().lower()
        if mode not in (MODE_OFF, MODE_HEAT):
            _LOGGER.warning("Invalid climate mode received: %s", payload)
            return

        _LOGGER.info("Thermostat %s mode changed to %s", self._id, mode)
        self._mode = mode

        if mode == MODE_OFF:
            self._action = ACTION_OFF
            await self._turn_output_off()
        else:
            self._action = ACTION_IDLE

        self._publish_state()

    async def handle_temperature_command(self, _topic: str, payload: str) -> None:
        """Handle target temperature command from HA.

        Args:
            _topic: MQTT topic (unused).
            payload: New target temperature string.
        """
        try:
            temp = float(payload)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid temperature value: %s", payload)
            return

        temp = max(self._min_temperature, min(self._max_temperature, temp))
        _LOGGER.info("Thermostat %s target temperature set to %.1f°C", self._id, temp)
        self._target_temperature = temp
        self._evaluate()
        self._publish_state()

    # -- Sensor update -------------------------------------------------------

    def update_temperature(self, temperature: float) -> None:
        """Update current temperature reading from sensor.

        Called by TemplateManager when a matching sensor event arrives.

        Args:
            temperature: Current temperature in °C.
        """
        self._current_temperature = temperature
        self._evaluate()
        self._publish_state()

    # -- Control logic -------------------------------------------------------

    def _evaluate(self) -> None:
        """Evaluate thermostat logic and control output.

        Uses bang-bang (hysteresis) control:
        - Turn ON when temp drops below (target - hysteresis)
        - Turn OFF when temp rises above (target + hysteresis)
        """
        if self._mode == MODE_OFF:
            if self._action != ACTION_OFF:
                self._action = ACTION_OFF
                asyncio.ensure_future(self._turn_output_off())
            return

        if self._current_temperature is None:
            return

        low = self._target_temperature - self._hysteresis
        high = self._target_temperature + self._hysteresis

        if self._current_temperature <= low:
            if self._action != ACTION_HEATING:
                self._action = ACTION_HEATING
                asyncio.ensure_future(self._turn_output_on())
                _LOGGER.debug(
                    "Thermostat %s: %.1f°C <= %.1f°C (low), heating ON",
                    self._id, self._current_temperature, low,
                )
        elif self._current_temperature >= high:
            if self._action != ACTION_IDLE:
                self._action = ACTION_IDLE
                asyncio.ensure_future(self._turn_output_off())
                _LOGGER.debug(
                    "Thermostat %s: %.1f°C >= %.1f°C (high), heating OFF",
                    self._id, self._current_temperature, high,
                )

    async def _turn_output_on(self) -> None:
        """Turn the heating output ON."""
        try:
            await self._output.async_turn_on()
        except Exception as err:
            _LOGGER.error("Failed to turn on output %s: %s", self._output.id, err)

    async def _turn_output_off(self) -> None:
        """Turn the heating output OFF."""
        try:
            await self._output.async_turn_off()
        except Exception as err:
            _LOGGER.error("Failed to turn off output %s: %s", self._output.id, err)

    # -- MQTT state publishing -----------------------------------------------

    def _publish_state(self) -> None:
        """Publish current thermostat state to MQTT."""
        payload: dict[str, Any] = {
            "mode": self._mode,
            "action": self._action,
            "target_temperature": self._target_temperature,
        }
        if self._current_temperature is not None:
            payload["current_temperature"] = round(self._current_temperature, 1)

        self._message_bus.send_message(
            topic=self._state_topic,
            payload=payload,
            retain=True,
        )

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start MQTT command subscriptions."""
        await self._message_bus.subscribe_and_listen(
            self._cmd_mode_topic, self.handle_mode_command
        )
        await self._message_bus.subscribe_and_listen(
            self._cmd_temp_topic, self.handle_temperature_command
        )
        self._publish_state()
        _LOGGER.info("Thermostat %s started", self._id)

    async def stop(self) -> None:
        """Stop MQTT command subscriptions."""
        try:
            await self._message_bus.unsubscribe_and_stop_listen(self._cmd_mode_topic)
            await self._message_bus.unsubscribe_and_stop_listen(self._cmd_temp_topic)
        except Exception:
            pass
        _LOGGER.info("Thermostat %s stopped", self._id)
