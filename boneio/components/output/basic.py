"""Basic Output module (formerly BasicRelay)."""

from __future__ import annotations

import asyncio
import logging
import time

from boneio.const import COVER, LIGHT, NONE, OFF, ON, OUTPUT, STATE, SWITCH
from boneio.core.events import EventBus, async_track_point_in_time, utcnow
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import callback
from boneio.core.utils.timeperiod import TimePeriod
from boneio.integration.interlock import SoftwareInterlockManager
from boneio.models import OutputState
from boneio.models.events import OutputEvent

_LOGGER = logging.getLogger(__name__)


class BasicOutput(BasicMqtt):
    """Basic output class (relay, switch, light, PWM).

    Formerly known as BasicRelay. This class represents any controllable
    output device in the BoneIO system.
    """

    # Subclasses (e.g. MCPOutput) will override these
    _pin_id: int = -1
    _expander_id: str | None = None

    def __init__(
        self,
        id: str,
        event_bus: EventBus,
        topic_prefix: str,
        name: str | None = None,
        output_type=SWITCH,
        restored_state: bool = False,
        topic_type: str = OUTPUT,
        interlock_manager: SoftwareInterlockManager | None = None,
        interlock_groups: list[str] | None = None,
        **kwargs,
    ) -> None:
        """Initialize Basic output."""
        if interlock_groups is None:
            interlock_groups = []
        self._momentary_turn_on = kwargs.pop("momentary_turn_on", None)
        self._momentary_turn_off = kwargs.pop("momentary_turn_off", None)

        # --- Adjustable duration (editable momentary_turn_on via HA number) ---
        self._adjustable_duration_enabled: bool = kwargs.pop("adjustable_duration", False)
        _dur_default_raw = kwargs.pop("duration_default", None)
        _dur_min_raw = kwargs.pop("duration_min", None)
        _dur_max_raw = kwargs.pop("duration_max", None)
        self._duration_unit: str = kwargs.pop("duration_unit", "s")
        # Pop legacy field in case it still exists in config
        kwargs.pop("duration_step", None)

        from boneio.core.utils.timeperiod import parse_time_to_seconds

        self._duration_min: float = max(1.0, parse_time_to_seconds(_dur_min_raw, 1.0))
        self._duration_max: float = max(self._duration_min, parse_time_to_seconds(_dur_max_raw, 3600.0))
        self._duration_default: float = parse_time_to_seconds(_dur_default_raw, 60.0)
        # Current adjustable duration value in seconds (will be overwritten by restored state)
        self._adjustable_duration: float = max(self._duration_min, min(self._duration_max, self._duration_default))

        super().__init__(id=id, name=name or id, topic_type=topic_type, topic_prefix=topic_prefix, **kwargs)
        self._output_type: str = output_type
        self._event_bus: EventBus = event_bus
        self._interlock_manager: SoftwareInterlockManager | None = interlock_manager
        self._interlock_groups: list[str] = interlock_groups
        if output_type == COVER:
            self._momentary_turn_on = None
            self._momentary_turn_off = None
            self._adjustable_duration_enabled = False
        self._state = ON if restored_state else OFF
        self._momentary_action = None
        self._last_timestamp = 0.0
        self._loop = asyncio.get_running_loop()

        # HA area/room assignment (set by OutputManager)
        self.area: str | None = None

    def set_interlock(self, interlock_manager: SoftwareInterlockManager, interlock_groups: list[str]):
        """Set interlock manager and groups."""
        self._interlock_manager = interlock_manager
        self._interlock_groups = interlock_groups

    @property
    def is_mcp_type(self) -> bool:
        """Check if relay is mcp type."""
        return False

    @property
    def output_type(self) -> str:
        """HA type."""
        return self._output_type

    @property
    def is_light(self) -> bool:
        """Check if HA type is light"""
        return self._output_type == LIGHT

    @property
    def id(self) -> str:
        """Id of the relay.
        Has to be trimmed out of spaces because of MQTT handling in HA."""
        return self._id or str(self._pin_id) or ""

    @property
    def name(self) -> str:
        """Not trimmed id."""
        return self._name or str(self._pin_id) or ""

    @property
    def pin_id(self) -> str | None:
        """Pin ID as string for OutputState model."""
        return str(self._pin_id) if self._pin_id is not None else None

    @property
    def state(self) -> str:
        """Is relay active."""
        return self._state

    @property
    def last_timestamp(self) -> float:
        return self._last_timestamp

    def payload(self) -> dict[str, str | float | int | None]:
        """Return payload for MQTT message.

        Returns:
            Dictionary with state information for MQTT publishing.
        """
        return {STATE: self.state}

    async def async_send_state(self, optimized_value: str | None = None) -> None:
        """Send state to Mqtt on action asynchronously."""
        if optimized_value:
            state = optimized_value
        else:
            state = ON if self.is_active else OFF
        self._state = state
        if self.output_type not in (COVER, NONE):
            self._message_bus.send_message(
                topic=self._send_topic,
                payload={STATE: state},
                retain=True,
            )
        if optimized_value:
            return
        self._last_timestamp = time.time()
        output_state = OutputState(
            id=self.id,
            name=self.name,
            state=state,
            type=self.output_type,
            pin=self.pin_id,
            timestamp=self.last_timestamp,
            expander_id=self.expander_id,
            area=self.area,
            interlock_groups=self._interlock_groups,
            adjustable_duration=self._adjustable_duration_enabled,
            adjustable_duration_value=self._adjustable_duration if self._adjustable_duration_enabled else None,
            duration_min=self._duration_min if self._adjustable_duration_enabled else None,
            duration_max=self._duration_max if self._adjustable_duration_enabled else None,
        )

        output_event = OutputEvent(
            entity_id=self.id,
            state=output_state,
        )
        self._event_bus.trigger_event(output_event)

    def check_interlock(self) -> bool:
        if self._interlock_manager is not None and self._interlock_groups:
            return self._interlock_manager.can_turn_on(self, self._interlock_groups)
        return True

    async def async_turn_on(self, timestamp=None) -> bool:
        """Turn on the relay asynchronously.

        Returns:
            True if the relay was turned on, False if blocked by interlock.
        """
        can_turn_on = self.check_interlock()
        if can_turn_on:
            try:
                await self._loop.run_in_executor(None, self.turn_on, timestamp)
            except RuntimeError as err:
                if "Executor shutdown" in str(err):
                    self.turn_on(timestamp)  # Fall back to sync during shutdown
                else:
                    raise
        else:
            _LOGGER.warning("Interlock active: cannot turn on %s.", self.id)
            # Workaround for HA is sendind state ON/OFF without physically changing the relay.
            asyncio.create_task(self.async_send_state(optimized_value=ON))
            await asyncio.sleep(0.01)
        asyncio.create_task(self.async_send_state())
        return can_turn_on

    async def async_turn_off(self, timestamp=None) -> None:
        """Turn off the relay asynchronously."""
        try:
            await self._loop.run_in_executor(None, self.turn_off, timestamp)
        except RuntimeError as err:
            if "Executor shutdown" in str(err):
                self.turn_off(timestamp)  # Fall back to sync during shutdown
            else:
                raise
        await self.async_send_state()

    async def async_toggle(self, timestamp=None) -> None:
        """Toggle relay."""
        now = time.time()
        _LOGGER.debug("Toggle relay %s, state: %s, at %s.", self.name, self.state, now)
        if self.state == ON:
            await self.async_turn_off(timestamp=timestamp)
        else:
            await self.async_turn_on(timestamp=timestamp)

    def turn_on(self, timestamp=None) -> None:
        """Call turn on action."""
        raise NotImplementedError

    def turn_off(self, timestamp=None) -> None:
        """Call turn off action."""
        raise NotImplementedError

    def set_brightness(self, value: int) -> None:
        """Set brightness (only supported on PWM outputs like PCA9685)."""
        _LOGGER.warning("set_brightness not supported for %s output type", self.output_type)

    def _execute_momentary_turn(self, momentary_type: str) -> None:
        """Execute momentary action.

        If adjustable_duration is enabled and this is a turn-ON action,
        use the dynamic duration instead of the static momentary_turn_on.
        """
        if self._momentary_action:
            _LOGGER.debug("Cancelling momentary action for %s", self.name)
            self._momentary_action()

        if momentary_type == ON:
            action = self.async_turn_off
            if self._adjustable_duration_enabled:
                # Use dynamic duration from HA number entity
                delayed_action = TimePeriod(seconds=self._adjustable_duration)
            else:
                delayed_action = self._momentary_turn_on
        else:
            action = self.async_turn_on
            delayed_action = self._momentary_turn_off

        if delayed_action:
            _LOGGER.debug("Applying momentary action for %s in %s", self.name, delayed_action.as_timedelta)
            self._momentary_action = async_track_point_in_time(
                loop=self._loop,
                job=self._momentary_callback,
                point_in_time=utcnow() + delayed_action.as_timedelta,
                action=action,
            )

    @callback
    async def _momentary_callback(self, timestamp, action):
        _LOGGER.info("Momentary callback at %s for output %s", timestamp, self.name)
        await action(timestamp=timestamp)
        self._momentary_action = None

    # -- Adjustable duration -------------------------------------------------

    @property
    def adjustable_duration_enabled(self) -> bool:
        """Whether this output has an adjustable duration (HA number entity)."""
        return self._adjustable_duration_enabled

    @property
    def adjustable_duration(self) -> float:
        """Current adjustable duration value in seconds."""
        return self._adjustable_duration

    @property
    def duration_min(self) -> float:
        """Minimum duration in seconds for HA slider."""
        return self._duration_min

    @property
    def duration_max(self) -> float:
        """Maximum duration in seconds for HA slider."""
        return self._duration_max

    @property
    def duration_unit(self) -> str:
        """Unit of measurement for HA number entity ('s' or 'min')."""
        return self._duration_unit

    def set_adjustable_duration(self, seconds: float) -> None:
        """Set the adjustable duration value.

        Clamps to [duration_min, duration_max].
        OutputManager handles persistence and MQTT publishing.

        Args:
            seconds: New duration in seconds.
        """
        self._adjustable_duration = max(self._duration_min, min(self._duration_max, seconds))
        _LOGGER.debug("Output '%s' adjustable duration set to %.1fs", self.id, self._adjustable_duration)

    def restore_adjustable_duration(self, seconds: float) -> None:
        """Restore persisted duration value (called during init by OutputManager).

        Args:
            seconds: Persisted duration value.
        """
        self._adjustable_duration = max(self._duration_min, min(self._duration_max, seconds))

    @property
    def is_active(self) -> bool:
        """Is active check."""
        raise NotImplementedError

    @property
    def expander_id(self) -> str | None:
        """Retrieve parent Expander ID (set by subclasses like MCPOutput)."""
        return self._expander_id
