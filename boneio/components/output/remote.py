"""Remote output base class for switches/lights on remote devices.

``RemoteOutputBase`` provides a duck-type compatible interface with
:class:`BasicOutput` so that :class:`OutputManager`, :class:`IrrigationController`,
and other consumers can treat remote outputs identically to local GPIO outputs.

The actual hardware control is delegated to the parent ``ESPHomeDeviceManager``
(or CAN/MQTT transport in the future).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from boneio.const import OFF, ON, OUTPUT, STATE, SWITCH
from boneio.core.events import EventBus, async_track_point_in_time, utcnow
from boneio.core.utils import callback
from boneio.core.utils.timeperiod import TimePeriod, parse_time_to_seconds
from boneio.models import OutputState
from boneio.models.events import OutputEvent

if TYPE_CHECKING:
    from boneio.core.messaging import MessageBus
    from boneio.integration.interlock import SoftwareInterlockManager

_LOGGER = logging.getLogger(__name__)


class RemoteOutputBase:
    """Common base class for remote / virtual output components.

    Provides the same public interface as ``BasicOutput`` so that
    any code doing ``output.async_turn_on()`` or checking ``output.state``
    will work transparently with remote outputs.

    Args:
        id: Entity identifier used in MQTT topics and state tracking.
        name: Human-readable display name.
        device_id: ID of the remote device hosting this output.
        output_id: Entity object_id on the remote device (e.g. ``relay_1``).
        remote_source: Transport protocol (``esphome_api``, ``can``, ``mqtt``).
        event_bus: Central event bus for emitting ``OutputEvent`` objects.
        output_type: HA entity type (``switch``, ``light``, ``valve``).
        show_in_ha: Whether to publish HA autodiscovery.
        area: Optional HA area assignment.
        on_disconnect: Behavior when remote device disconnects
            (``ignore`` or ``turn_off``).
    """

    # Duck-type compatibility flags
    _pin_id: int = -1
    _expander_id: str | None = None

    def __init__(
        self,
        *,
        id: str,
        name: str,
        device_id: str,
        output_id: str,
        remote_source: str,
        event_bus: EventBus,
        message_bus: MessageBus | None = None,
        topic_prefix: str = "",
        output_type: str = SWITCH,
        show_in_ha: bool = False,
        area: str | None = None,
        on_disconnect: str = "ignore",
        interlock_manager: SoftwareInterlockManager | None = None,
        interlock_groups: list[str] | None = None,
        enforce_interlock: bool = False,
        momentary_turn_on: TimePeriod | None = None,
        momentary_turn_off: TimePeriod | None = None,
        adjustable_duration: bool = False,
        duration_default: float = 60.0,
        duration_min: float = 1.0,
        duration_max: float = 3600.0,
        duration_unit: str = "s",
        supports_brightness: bool = False,
    ) -> None:
        self._id = id
        self._name = name
        self._device_id = device_id
        self._output_id = output_id
        self._remote_source = remote_source
        self._event_bus = event_bus
        self._message_bus: MessageBus | None = message_bus
        self._send_topic = f"{topic_prefix}/{OUTPUT}/{id}" if topic_prefix else ""
        self._output_type = output_type
        self.show_in_ha = show_in_ha
        self.area: str | None = area
        self._on_disconnect = on_disconnect

        # Interlock support (shared with local BasicOutput instances)
        self._interlock_manager: SoftwareInterlockManager | None = interlock_manager
        self._interlock_groups: list[str] = interlock_groups or []
        self._enforce_interlock: bool = enforce_interlock

        # Momentary actions (auto-off / auto-on after duration)
        self._momentary_turn_on: TimePeriod | None = momentary_turn_on
        self._momentary_turn_off: TimePeriod | None = momentary_turn_off
        self._momentary_action: Any = None

        # Adjustable duration (HA number entity slider)
        self._adjustable_duration_enabled: bool = adjustable_duration
        self._duration_min: float = max(1.0, duration_min)
        self._duration_max: float = max(self._duration_min, duration_max)
        self._duration_default: float = duration_default
        self._duration_unit: str = duration_unit
        self._adjustable_duration: float = max(self._duration_min, min(self._duration_max, self._duration_default))
        # If adjustable_duration is on, momentary_turn_on is managed by the slider
        if self._adjustable_duration_enabled:
            self._momentary_turn_on = None

        self._state: str = OFF
        self._last_timestamp: float = 0.0
        self._available: bool = False
        self._supports_brightness: bool = supports_brightness
        self._brightness: int | None = None  # 0-255, None if not a dimmable light
        self._loop: asyncio.AbstractEventLoop | None = None

        # Reference to remote device manager — set by register_remote_outputs().
        # May be None at startup if ESPHome devices load in background.
        self._device_manager: Any = None
        # Fallback reference to resolve device manager lazily.
        self._remote_devices_ref: Any = None

    # ------------------------------------------------------------------
    # Lazy device manager resolution
    # ------------------------------------------------------------------

    def _resolve_device_manager(self) -> bool:
        """Try to resolve device manager lazily from remote_devices reference.

        Returns:
            ``True`` if device manager is now available.
        """
        if self._device_manager is not None:
            return True
        if self._remote_devices_ref is None:
            return False
        device = self._remote_devices_ref.get_device(self._device_id)
        if device is not None:
            self._device_manager = device
            self._remote_devices_ref = None  # No longer needed
            self._register_state_callback()
            _LOGGER.info(
                "Lazily resolved device manager for remote output '%s' (device '%s')",
                self._id,
                self._device_id,
            )
            return True
        return False

    def _register_state_callback(self) -> None:
        """Register a state change callback on the device manager.

        Called after device manager is resolved (lazy or immediate).
        ESPHome devices will call back on switch/light state changes,
        updating brightness and state on this output.
        Also syncs current state from the device if available.
        """
        if self._device_manager is None:
            return
        register_fn = getattr(self._device_manager, "register_output_callback", None)
        if register_fn is not None:
            register_fn(self._output_id, self.on_remote_state_change)
            _LOGGER.debug(
                "Registered state callback for remote output '%s' on device '%s'",
                self._id,
                self._device_id,
            )

        # Sync initial state from device's current known states
        self._sync_initial_state()

    def _sync_initial_state(self) -> None:
        """Sync initial state from device manager's current known states.

        Reads cached states from ESPHome (_light_states / _switch_states)
        or WLED (_cached_state) to populate brightness and on/off state
        immediately, without waiting for the next state change event.
        """
        if self._device_manager is None:
            return

        # WLED: sync from WebSocket cached state
        get_output_is_on = getattr(self._device_manager, "get_output_is_on", None)
        if get_output_is_on is not None:
            is_on = get_output_is_on(self._output_id)
            if is_on is not None:
                self.on_remote_state_change(is_on)
                _LOGGER.debug(
                    "Synced initial WLED state for '%s': on=%s",
                    self._id,
                    is_on,
                )
                return

        # ESPHome: try light state first
        light_states = getattr(self._device_manager, "_light_states", {})
        _LOGGER.debug(
            "Sync initial state for '%s': output_id='%s', light_states_keys=%s, switch_states_keys=%s",
            self._id,
            self._output_id,
            list(light_states.keys()),
            list(getattr(self._device_manager, "_switch_states", {}).keys()),
        )
        if self._output_id in light_states:
            ls = light_states[self._output_id]
            is_on = ls.get("state", False)
            raw_brightness = ls.get("brightness", 0.0)
            brightness_255 = int(round(raw_brightness * 255)) if is_on else 0
            self.on_remote_state_change(is_on, brightness=brightness_255)
            _LOGGER.debug(
                "Synced initial light state for '%s': on=%s brightness=%d",
                self._id,
                is_on,
                brightness_255,
            )
            return

        # ESPHome: try switch state
        switch_states = getattr(self._device_manager, "_switch_states", {})
        if self._output_id in switch_states:
            is_on = switch_states[self._output_id]
            self.on_remote_state_change(is_on)
            _LOGGER.debug(
                "Synced initial switch state for '%s': on=%s",
                self._id,
                is_on,
            )
            return

        # If output supports brightness, initialize brightness to 0 so the
        # slider renders immediately (will update on first state event).
        if self._supports_brightness:
            self._brightness = 0
            _LOGGER.debug(
                "Initialized brightness=0 for remote light '%s' (no state yet)",
                self._id,
            )

    # ------------------------------------------------------------------
    # Interlock
    # ------------------------------------------------------------------

    def set_interlock(
        self,
        interlock_manager: SoftwareInterlockManager,
        interlock_groups: list[str],
    ) -> None:
        """Set interlock manager and groups.

        Args:
            interlock_manager: Shared interlock manager instance.
            interlock_groups: List of group names this output belongs to.
        """
        self._interlock_manager = interlock_manager
        self._interlock_groups = interlock_groups

    def check_interlock(self) -> bool:
        """Check if this output can be turned on without violating interlocks.

        Returns:
            True if no interlock violation, False if blocked.
        """
        if self._interlock_manager is not None and self._interlock_groups:
            return self._interlock_manager.can_turn_on(self, self._interlock_groups)
        return True

    # ------------------------------------------------------------------
    # Core control methods (duck-type compatible with BasicOutput)
    # ------------------------------------------------------------------

    async def async_turn_on(self, timestamp: float | None = None) -> bool:
        """Turn on the remote output.

        Checks interlock before sending the ON command. If another output
        in the same interlock group is already ON, the request is rejected.
        After successful ON, schedules momentary auto-OFF if configured.

        Args:
            timestamp: Optional timestamp for state tracking.

        Returns:
            True if the output was turned on, False if blocked or failed.
        """
        can_turn_on = self.check_interlock()
        if not can_turn_on:
            _LOGGER.warning("Interlock active: cannot turn on remote output '%s'", self._id)
            return False

        if not self._resolve_device_manager():
            _LOGGER.error("Remote output '%s' has no device manager, cannot turn on", self._id)
            return False

        success = await self._device_manager.control_output(
            output_id=self._output_id,
            action="ON",
        )
        if success:
            self._state = ON
            self._last_timestamp = timestamp or time.time()
            self._emit_state_event()
            self._execute_momentary_turn(ON)
            _LOGGER.debug("Remote output '%s' turned ON", self._id)
        else:
            _LOGGER.warning("Failed to turn ON remote output '%s'", self._id)
        return success

    async def async_turn_off(self, timestamp: float | None = None) -> None:
        """Turn off the remote output.

        After successful OFF, schedules momentary auto-ON if configured.

        Args:
            timestamp: Optional timestamp for state tracking.
        """
        if not self._resolve_device_manager():
            _LOGGER.error("Remote output '%s' has no device manager, cannot turn off", self._id)
            return

        success = await self._device_manager.control_output(
            output_id=self._output_id,
            action="OFF",
        )
        if success:
            self._state = OFF
            self._last_timestamp = timestamp or time.time()
            self._emit_state_event()
            self._execute_momentary_turn(OFF)
            _LOGGER.debug("Remote output '%s' turned OFF", self._id)
        else:
            _LOGGER.warning("Failed to turn OFF remote output '%s'", self._id)

    async def async_toggle(self, timestamp: float | None = None) -> None:
        """Toggle the remote output.

        Args:
            timestamp: Optional timestamp for state tracking.
        """
        if self._state == ON:
            await self.async_turn_off(timestamp=timestamp)
        else:
            await self.async_turn_on(timestamp=timestamp)

    # ------------------------------------------------------------------
    # State change from remote device (callback)
    # ------------------------------------------------------------------

    def on_remote_state_change(self, new_state: bool, brightness: int | None = None) -> None:
        """Handle state change reported by the remote device.

        Called by ESPHomeDeviceManager when it receives a state update
        for this output's entity.

        If ``enforce_interlock`` is enabled and the output was turned ON
        externally while violating an interlock, boneIO will immediately
        send a turn-off command.

        Args:
            new_state: ``True`` if the output is now ON.
            brightness: Optional brightness value (0-255) for dimmable lights.
        """
        new_state_str = ON if new_state else OFF
        changed = new_state_str != self._state or brightness != self._brightness

        if not changed:
            return

        self._state = new_state_str
        if brightness is not None:
            self._brightness = brightness
        self._last_timestamp = time.time()
        self._emit_state_event()
        _LOGGER.debug(
            "Remote output '%s' state changed to %s brightness=%s (from device)",
            self._id,
            self._state,
            self._brightness,
        )

        # Enforce interlock: if turned ON externally and violating interlock,
        # immediately send OFF command to the remote device.
        if new_state and self._enforce_interlock and not self.check_interlock():
            _LOGGER.warning(
                "Remote output '%s' turned ON externally, violating interlock — forcing OFF",
                self._id,
            )
            asyncio.ensure_future(self._enforce_interlock_off())

    async def async_set_brightness(self, brightness: int, timestamp: float | None = None) -> None:
        """Set brightness on the remote light output.

        Checks interlock before sending the brightness command. Setting
        brightness implicitly turns the light ON, so interlock rules apply.

        Args:
            brightness: Brightness value (0-255).
            timestamp: Optional timestamp for state tracking.
        """
        # Brightness > 0 effectively turns ON — must check interlock
        if brightness > 0 and not self.check_interlock():
            _LOGGER.warning(
                "Interlock active: cannot set brightness on remote output '%s'",
                self._id,
            )
            return

        if not self._resolve_device_manager():
            _LOGGER.error("Remote output '%s' has no device manager, cannot set brightness", self._id)
            return

        success = await self._device_manager.control_output(
            output_id=self._output_id,
            action="ON",
            brightness=brightness,
        )
        if success:
            self._state = ON
            self._brightness = brightness
            self._last_timestamp = timestamp or time.time()
            self._emit_state_event()
            _LOGGER.debug("Remote output '%s' brightness set to %d", self._id, brightness)
        else:
            _LOGGER.warning("Failed to set brightness on remote output '%s'", self._id)

    def on_device_availability_change(self, available: bool) -> None:
        """Handle device connectivity change.

        Called when the remote device connects or disconnects.

        Args:
            available: ``True`` if device is now connected.
        """
        was_available = self._available
        self._available = available

        if not available and was_available:
            _LOGGER.warning(
                "Remote device '%s' disconnected (output '%s', policy: %s)",
                self._device_id,
                self._id,
                self._on_disconnect,
            )
            if self._on_disconnect == "turn_off" and self._state == ON:
                _LOGGER.info("Forcing remote output '%s' OFF due to disconnect policy", self._id)
                self._state = OFF
                self._last_timestamp = time.time()
                self._emit_state_event()
        elif available and not was_available:
            _LOGGER.info(
                "Remote device '%s' reconnected (output '%s')",
                self._device_id,
                self._id,
            )
            # If disconnect policy was turn_off, enforce OFF on the real device
            # because during disconnect we only changed local state.
            if self._on_disconnect == "turn_off" and self._state == OFF:
                import asyncio

                asyncio.ensure_future(self._enforce_off_after_reconnect())

    # ------------------------------------------------------------------
    # Reconnect enforcement
    # ------------------------------------------------------------------

    async def _enforce_off_after_reconnect(self) -> None:
        """Send OFF command to remote device after reconnection.

        During disconnect, we only changed the local state to OFF.
        Now that the device is back, send the real OFF command to ensure
        the physical relay matches our local state.
        """
        if self._device_manager is None:
            return
        _LOGGER.info(
            "Enforcing OFF on remote output '%s' after reconnect (turn_off policy)",
            self._id,
        )
        success = await self._device_manager.control_output(
            output_id=self._output_id,
            action="OFF",
        )
        if not success:
            _LOGGER.warning(
                "Failed to enforce OFF on remote output '%s' after reconnect",
                self._id,
            )

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit_state_event(self) -> None:
        """Emit OutputEvent on EventBus for WebSocket/state tracking.

        Also publishes the current state to the MQTT state topic so that
        Home Assistant (and any other MQTT consumer) sees the updated state.
        """
        # Publish state to MQTT so HA sees the update
        if self._message_bus and self._send_topic:
            payload: dict[str, Any] = {STATE: self._state}
            if self._brightness is not None:
                payload["brightness"] = self._brightness
            self._message_bus.send_message(
                topic=self._send_topic,
                payload=payload,
                retain=True,
            )

        output_state = OutputState(
            id=self._id,
            name=self._name,
            state=self._state,
            type=self._output_type,
            pin=None,
            expander_id=None,
            timestamp=self._last_timestamp,
            area=self.area,
            remote=True,
            brightness=self._brightness,
            interlock_groups=self._interlock_groups,
        )
        self._event_bus.trigger_event(OutputEvent(entity_id=self._id, state=output_state))

    # ------------------------------------------------------------------
    # Momentary actions (auto-off / auto-on after delay)
    # ------------------------------------------------------------------

    def _execute_momentary_turn(self, momentary_type: str) -> None:
        """Schedule momentary action (auto-off after ON, or auto-on after OFF).

        If adjustable_duration is enabled and this is a turn-ON action,
        the slider value is used instead of the static momentary_turn_on.

        Args:
            momentary_type: ON or OFF.
        """
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                return

        if self._momentary_action:
            _LOGGER.debug("Cancelling momentary action for %s", self._name)
            self._momentary_action()

        if momentary_type == ON:
            action = self.async_turn_off
            if self._adjustable_duration_enabled:
                delayed_action = TimePeriod(seconds=self._adjustable_duration)
            else:
                delayed_action = self._momentary_turn_on
        else:
            action = self.async_turn_on
            delayed_action = self._momentary_turn_off

        if delayed_action:
            _LOGGER.debug(
                "Scheduling momentary action for %s in %s",
                self._name,
                delayed_action.as_timedelta,
            )
            self._momentary_action = async_track_point_in_time(
                loop=self._loop,
                job=self._momentary_callback,
                point_in_time=utcnow() + delayed_action.as_timedelta,
                action=action,
            )

    @callback
    async def _momentary_callback(self, timestamp: float, action: Any) -> None:
        """Execute the scheduled momentary turn-on or turn-off."""
        _LOGGER.info("Momentary callback at %s for remote output %s", timestamp, self._name)
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

        Args:
            seconds: New duration in seconds.
        """
        self._adjustable_duration = max(self._duration_min, min(self._duration_max, seconds))
        _LOGGER.debug(
            "Remote output '%s' adjustable duration set to %.1fs",
            self.id,
            self._adjustable_duration,
        )

    def restore_adjustable_duration(self, seconds: float) -> None:
        """Restore persisted duration value.

        Args:
            seconds: Persisted duration value.
        """
        self._adjustable_duration = max(self._duration_min, min(self._duration_max, seconds))

    async def _enforce_interlock_off(self) -> None:
        """Send OFF command to remote device after interlock violation.

        Called when the remote device reports ON state that violates an
        active interlock group. Small delay allows the state to settle.
        """
        await asyncio.sleep(0.1)  # Allow state to settle
        if not self._resolve_device_manager():
            _LOGGER.error(
                "Cannot enforce interlock OFF on '%s': no device manager",
                self._id,
            )
            return
        success = await self._device_manager.control_output(
            output_id=self._output_id,
            action="OFF",
        )
        if success:
            _LOGGER.info("Interlock enforced: remote output '%s' turned OFF", self._id)
        else:
            _LOGGER.error(
                "Failed to enforce interlock OFF on remote output '%s'",
                self._id,
            )

    # ------------------------------------------------------------------
    # Properties (duck-type compatible with BasicOutput)
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        """Entity identifier."""
        return self._id

    @property
    def name(self) -> str:
        """Human-readable name."""
        return self._name

    @property
    def state(self) -> str:
        """Current state ('ON' or 'OFF')."""
        return self._state

    @property
    def output_type(self) -> str:
        """HA entity type (switch, light, valve)."""
        return self._output_type

    @property
    def is_active(self) -> bool:
        """Whether the output is currently ON."""
        return self._state == ON

    @property
    def available(self) -> bool:
        """Whether the remote device is connected."""
        return self._available

    @property
    def last_timestamp(self) -> float:
        """Unix timestamp of last state change."""
        return self._last_timestamp

    @property
    def pin_id(self) -> str | None:
        """Pin ID — always None for remote outputs."""
        return None

    @property
    def expander_id(self) -> str | None:
        """Expander ID — always None for remote outputs."""
        return None

    @property
    def is_light(self) -> bool:
        """Check if output type is light."""
        return self._output_type == "light"

    @property
    def is_mcp_type(self) -> bool:
        """Check if relay is MCP type — always False for remote."""
        return False

    @property
    def device_id(self) -> str:
        """ID of the remote device hosting this output."""
        return self._device_id

    @property
    def output_id_on_device(self) -> str:
        """Entity object_id on the remote device."""
        return self._output_id

    @property
    def remote_source(self) -> str:
        """Transport protocol (esphome_api, can, mqtt)."""
        return self._remote_source

    @property
    def on_disconnect(self) -> str:
        """Disconnect behavior policy."""
        return self._on_disconnect

    @property
    def is_remote(self) -> bool:
        """Whether this is a remote output — always True."""
        return True

    # ------------------------------------------------------------------
    # Adjustable duration stubs (remote outputs don't support this)
    # ------------------------------------------------------------------

    @property
    def adjustable_duration_enabled(self) -> bool:
        """Remote outputs don't support adjustable duration."""
        return False

    @property
    def adjustable_duration(self) -> float:
        """Not applicable for remote outputs."""
        return 0.0

    @property
    def duration_min(self) -> float:
        """Not applicable for remote outputs."""
        return 0.0

    @property
    def duration_max(self) -> float:
        """Not applicable for remote outputs."""
        return 0.0

    @property
    def duration_unit(self) -> str:
        """Not applicable for remote outputs."""
        return "s"

    def __repr__(self) -> str:
        return (
            f"<RemoteOutputBase id={self._id!r} device={self._device_id!r} "
            f"output={self._output_id!r} state={self._state} "
            f"available={self._available}>"
        )
