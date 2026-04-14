"""Timed Output template component.

An output with an adjustable timer — turns ON for N seconds, then auto-OFF.
The duration is editable from Home Assistant via a number entity (slider/box).

Use cases:
- Manual garden irrigation: set watering time → press ON → auto-OFF
- Timed lighting: porch light for 10 minutes
- Valve control: open valve for N seconds
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from boneio.const import OFF, ON, STATE
from boneio.core.events import async_track_point_in_time, utcnow

if TYPE_CHECKING:
    from boneio.components.output.basic import BasicOutput
    from boneio.core.events import EventBus
    from boneio.core.state import StateManager

_LOGGER = logging.getLogger(__name__)

# State persistence key prefix
_STATE_PREFIX = "timed_output"


class TimedOutput:
    """Output with adjustable timer — turns ON for set duration, then auto-OFF.

    Creates two HA entities:
    1. Switch/Valve/Light — controls the physical output
    2. Number — adjustable duration slider (persisted in state.json)

    Args:
        id: Unique entity identifier.
        name: Human-readable name for HA.
        output: Reference to the underlying BasicOutput relay.
        message_bus: MQTT message bus for publishing state.
        event_bus: EventBus for scheduling timers.
        state_manager: StateManager for persisting duration.
        topic_prefix: MQTT topic prefix (e.g., "boneio").
        default_duration: Default duration in seconds.
        min_duration: Minimum allowed duration in seconds.
        max_duration: Maximum allowed duration in seconds.
        step: Duration adjustment step for HA slider.
        unit: Unit of measurement ("s" or "min").
        icon: MDI icon for HA (optional).
        area: Area/room ID (optional).
    """

    def __init__(
        self,
        id: str,
        name: str,
        output: BasicOutput,
        message_bus: Any,
        event_bus: EventBus,
        state_manager: StateManager,
        topic_prefix: str,
        default_duration: int = 60,
        min_duration: int = 1,
        max_duration: int = 3600,
        step: int = 1,
        unit: str = "s",
        icon: str | None = None,
        area: str | None = None,
    ) -> None:
        self._id = id
        self._name = name
        self._output = output
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._state_manager = state_manager
        self._topic_prefix = topic_prefix

        self._min_duration = max(1, int(min_duration))
        self._max_duration = max(self._min_duration, int(max_duration))
        self._step = max(1, int(step))
        self._unit = unit
        self._icon = icon
        self._area = area

        # Restore persisted duration or use default
        saved = self._state_manager.get(
            _STATE_PREFIX, f"{self._id}/duration", None
        )
        if saved is not None:
            self._duration = max(
                self._min_duration,
                min(self._max_duration, int(saved)),
            )
        else:
            self._duration = max(
                self._min_duration,
                min(self._max_duration, int(default_duration)),
            )

        self._timer_cancel = None
        self._is_running = False

        _LOGGER.debug(
            "TimedOutput '%s' initialized: duration=%ds, range=[%d-%d], output=%s",
            self._id, self._duration, self._min_duration, self._max_duration,
            self._output.id,
        )

    # -- Properties ----------------------------------------------------------

    @property
    def id(self) -> str:
        """Unique entity ID."""
        return self._id

    @property
    def name(self) -> str:
        """Human-readable name."""
        return self._name

    @property
    def duration(self) -> int:
        """Current duration in seconds."""
        return self._duration

    @property
    def min_duration(self) -> int:
        """Minimum duration in seconds."""
        return self._min_duration

    @property
    def max_duration(self) -> int:
        """Maximum duration in seconds."""
        return self._max_duration

    @property
    def step(self) -> int:
        """Duration adjustment step."""
        return self._step

    @property
    def unit(self) -> str:
        """Unit of measurement."""
        return self._unit

    @property
    def icon(self) -> str | None:
        """MDI icon."""
        return self._icon

    @property
    def area(self) -> str | None:
        """Area/room ID."""
        return self._area

    @property
    def output(self) -> BasicOutput:
        """Underlying output reference."""
        return self._output

    @property
    def output_type(self) -> str:
        """Output type of the underlying output (switch/light/valve)."""
        return self._output.output_type

    @property
    def is_running(self) -> bool:
        """Whether the timed output is currently active."""
        return self._is_running

    # -- MQTT topics ---------------------------------------------------------

    def _state_topic(self) -> str:
        return f"{self._topic_prefix}/timed_output/{self._id}"

    def _cmd_topic(self) -> str:
        return f"{self._topic_prefix}/cmd/timed_output/{self._id}/set"

    def _duration_state_topic(self) -> str:
        return f"{self._topic_prefix}/timed_output/{self._id}/duration"

    def _duration_cmd_topic(self) -> str:
        return f"{self._topic_prefix}/cmd/timed_output/{self._id}/duration/set"

    # -- Actions -------------------------------------------------------------

    async def turn_on(self) -> None:
        """Turn on the output for the configured duration.

        If already running, restarts the timer with current duration.
        """
        self._cancel_timer()

        try:
            await self._output.async_turn_on()
        except Exception as err:
            _LOGGER.error("TimedOutput '%s': failed to turn on output: %s", self._id, err)
            return

        self._is_running = True
        await self._publish_state()

        # Arm auto-off timer
        point = utcnow() + timedelta(seconds=self._duration)
        self._timer_cancel = async_track_point_in_time(
            loop=self._event_bus.loop,
            job=self._timer_callback,
            point_in_time=point,
        )

        _LOGGER.info(
            "TimedOutput '%s' turned ON for %ds (output: %s)",
            self._id, self._duration, self._output.id,
        )

    async def turn_off(self) -> None:
        """Turn off the output and cancel any active timer."""
        self._cancel_timer()

        try:
            await self._output.async_turn_off()
        except Exception as err:
            _LOGGER.error("TimedOutput '%s': failed to turn off output: %s", self._id, err)

        self._is_running = False
        await self._publish_state()

        _LOGGER.info("TimedOutput '%s' turned OFF", self._id)

    async def set_duration(self, seconds: int) -> None:
        """Set the timer duration.

        Clamps value to [min_duration, max_duration] and persists to state.json.
        Does NOT restart the output if currently running.

        Args:
            seconds: New duration in seconds.
        """
        clamped = max(self._min_duration, min(self._max_duration, int(seconds)))
        self._duration = clamped
        self._state_manager.save_attribute(
            _STATE_PREFIX, f"{self._id}/duration", self._duration
        )
        await self._publish_duration()

        _LOGGER.debug("TimedOutput '%s' duration set to %ds", self._id, self._duration)

    # -- MQTT publishing -----------------------------------------------------

    async def _publish_state(self) -> None:
        """Publish the switch/valve state to MQTT."""
        state = ON if self._is_running else OFF
        self._message_bus.send_message(
            topic=self._state_topic(),
            payload={STATE: state},
            retain=True,
        )

    async def _publish_duration(self) -> None:
        """Publish the duration number value to MQTT."""
        self._message_bus.send_message(
            topic=self._duration_state_topic(),
            payload={"value": self._duration},
            retain=True,
        )

    async def publish_all_states(self) -> None:
        """Publish both switch state and duration value."""
        await self._publish_state()
        await self._publish_duration()

    # -- MQTT command handling -----------------------------------------------

    async def handle_command(self, payload: str) -> None:
        """Handle ON/OFF command from MQTT.

        Args:
            payload: "ON" or "OFF" string.
        """
        cmd = payload.strip().upper()
        if cmd == ON:
            await self.turn_on()
        elif cmd == OFF:
            await self.turn_off()
        else:
            _LOGGER.warning("TimedOutput '%s': unknown command '%s'", self._id, cmd)

    async def handle_duration_command(self, payload: str) -> None:
        """Handle duration change from MQTT number entity.

        Args:
            payload: Duration value as string (seconds).
        """
        try:
            value = int(float(payload))
        except (TypeError, ValueError):
            _LOGGER.warning(
                "TimedOutput '%s': invalid duration value '%s'", self._id, payload
            )
            return
        await self.set_duration(value)

    # -- Timer management ----------------------------------------------------

    def _cancel_timer(self) -> None:
        """Cancel any active auto-off timer."""
        if self._timer_cancel is not None:
            self._timer_cancel()
            self._timer_cancel = None

    async def _timer_callback(self, _timestamp) -> None:
        """Called when the timer expires — auto-turn-off."""
        _LOGGER.info("TimedOutput '%s' timer expired, turning OFF", self._id)
        self._timer_cancel = None
        await self.turn_off()

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start the component: publish initial state.

        Note: MQTT subscriptions are managed by TimedOutputManager,
        not by the component itself (consistent with IrrigationManager pattern).
        """
        await self.publish_all_states()
        _LOGGER.info("TimedOutput '%s' started (output: %s)", self._id, self._output.id)

    async def stop(self) -> None:
        """Stop the component: cancel timer and turn off output."""
        self._cancel_timer()
        if self._is_running:
            try:
                await self._output.async_turn_off()
            except Exception as err:
                _LOGGER.error("TimedOutput '%s': error on stop: %s", self._id, err)
        self._is_running = False

