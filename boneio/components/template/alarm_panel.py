"""BoneIO Alarm Control Panel — zone-based alarm system.

Monitors input zones, manages arm/disarm state machine with timers,
and controls output devices (siren, notification, etc.) on trigger.

Exposed to Home Assistant as ``alarm_control_panel`` entity via MQTT
autodiscovery.  Code validation is delegated to HA (``REMOTE_CODE``).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from boneio.const import ALARM_CONTROL_PANEL, STATE

if TYPE_CHECKING:
    from boneio.core.messaging.basic import MessageBus
    from boneio.core.events.bus import EventBus
    from boneio.components.output.basic import BasicOutput

_LOGGER = logging.getLogger(__name__)

# HA alarm states
DISARMED = "disarmed"
ARMING = "arming"
ARMED_HOME = "armed_home"
ARMED_AWAY = "armed_away"
ARMED_NIGHT = "armed_night"
PENDING = "pending"
TRIGGERED = "triggered"

# HA alarm commands (received from HA)
CMD_ARM_HOME = "ARM_HOME"
CMD_ARM_AWAY = "ARM_AWAY"
CMD_ARM_NIGHT = "ARM_NIGHT"
CMD_DISARM = "DISARM"
CMD_TRIGGER = "TRIGGER"

# Output types
OUTPUT_SIREN = "siren"
OUTPUT_NOTIFICATION = "notification"
OUTPUT_LIGHT = "light"
OUTPUT_CUSTOM = "custom"


class AlarmZone:
    """A zone groups inputs and defines which arm modes activate them.

    Args:
        name: Human-readable zone name.
        input_ids: List of input entity IDs to monitor.
        arm_modes: List of arm modes where this zone is active.
        entry_delay: Whether this zone uses entry delay before triggering.
    """

    def __init__(
        self,
        name: str,
        input_ids: list[str],
        arm_modes: list[str],
        entry_delay: bool = False,
    ) -> None:
        self.name = name
        self.input_ids = input_ids
        self.arm_modes = arm_modes
        self.entry_delay = entry_delay

    def is_active_in_mode(self, mode: str) -> bool:
        """Check if this zone is active in the given arm mode.

        Args:
            mode: Current alarm arm mode.

        Returns:
            True if the zone should be monitored in this mode.
        """
        return mode in self.arm_modes


class AlarmOutput:
    """An output controlled by the alarm panel.

    Args:
        output: The physical output (relay) to control.
        output_type: Type of output (siren, notification, light, custom).
    """

    def __init__(self, output: "BasicOutput", output_type: str = OUTPUT_SIREN) -> None:
        self.output = output
        self.output_type = output_type


class BoneIOAlarmPanel:
    """Zone-based alarm control panel with state machine.

    Args:
        id: Unique alarm panel identifier.
        name: Human-readable name for HA.
        message_bus: MessageBus for MQTT communication.
        event_bus: EventBus for internal events.
        topic_prefix: MQTT topic prefix.
        zones: List of AlarmZone definitions.
        outputs: List of AlarmOutput definitions.
        arming_time_s: Seconds to wait in arming state before armed.
        delay_time_s: Seconds to wait in pending state before triggered.
        trigger_time_s: Seconds the alarm stays triggered before auto-disarm.
        area: Optional area ID for HA sub-device.
    """

    def __init__(
        self,
        id: str,
        name: str,
        message_bus: "MessageBus",
        event_bus: "EventBus",
        topic_prefix: str,
        zones: list[AlarmZone],
        outputs: list[AlarmOutput],
        arming_time_s: float = 30.0,
        delay_time_s: float = 30.0,
        trigger_time_s: float = 300.0,
        area: str | None = None,
    ) -> None:
        self._id = id
        self._name = name
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._topic_prefix = topic_prefix
        self._zones = zones
        self._outputs = outputs
        self._arming_time_s = arming_time_s
        self._delay_time_s = delay_time_s
        self._trigger_time_s = trigger_time_s
        self._area = area

        # State
        self._state = DISARMED
        self._pending_arm_mode: str | None = None

        # Timers
        self._arming_timer: asyncio.TimerHandle | None = None
        self._delay_timer: asyncio.TimerHandle | None = None
        self._trigger_timer: asyncio.TimerHandle | None = None

        # MQTT topics
        self._state_topic = f"{topic_prefix}/alarm/{id}/{STATE}"
        self._cmd_topic = f"{topic_prefix}/cmd/alarm/{id}/set"

        # Track triggered inputs for logging
        self._triggered_zone: str | None = None
        self._triggered_input: str | None = None

        _LOGGER.info(
            "Initialized BoneIOAlarmPanel: id=%s, zones=%d, outputs=%d, "
            "arming=%.0fs, delay=%.0fs, trigger=%.0fs",
            id, len(zones), len(outputs),
            arming_time_s, delay_time_s, trigger_time_s,
        )

    # -- Properties ----------------------------------------------------------

    @property
    def id(self) -> str:
        """Get alarm panel ID."""
        return self._id

    @property
    def name(self) -> str:
        """Get alarm panel name."""
        return self._name

    @property
    def area(self) -> str | None:
        """Get area ID."""
        return self._area

    @property
    def state(self) -> str:
        """Get current alarm state."""
        return self._state

    @property
    def zones(self) -> list[AlarmZone]:
        """Get alarm zones."""
        return self._zones

    @property
    def outputs(self) -> list[AlarmOutput]:
        """Get alarm outputs."""
        return self._outputs

    # -- MQTT command handler ------------------------------------------------

    async def handle_command(self, _topic: str, payload: str) -> None:
        """Handle alarm command from HA.

        Args:
            _topic: MQTT topic (unused).
            payload: Command string (ARM_HOME, ARM_AWAY, ARM_NIGHT, DISARM, TRIGGER).
        """
        command = payload.strip().upper()
        _LOGGER.info("Alarm %s received command: %s (current state: %s)",
                      self._id, command, self._state)

        if command == CMD_DISARM:
            await self._disarm()
        elif command == CMD_ARM_HOME:
            await self._arm(ARMED_HOME)
        elif command == CMD_ARM_AWAY:
            await self._arm(ARMED_AWAY)
        elif command == CMD_ARM_NIGHT:
            await self._arm(ARMED_NIGHT)
        elif command == CMD_TRIGGER:
            await self._trigger("manual", "manual")
        else:
            _LOGGER.warning("Unknown alarm command: %s", command)

    # -- Input event handler -------------------------------------------------

    def on_input_event(self, input_id: str, event_type: str) -> None:
        """Handle input sensor event (pressed/released).

        Called by TemplateManager when a monitored input fires.

        Args:
            input_id: The input entity ID that fired.
            event_type: Event type (e.g. 'pressed', 'single').
        """
        if self._state == DISARMED:
            return

        if self._state in (ARMING, PENDING, TRIGGERED):
            return

        # Check if any active zone contains this input
        for zone in self._zones:
            if input_id not in zone.input_ids:
                continue
            if not zone.is_active_in_mode(self._state):
                continue

            _LOGGER.warning(
                "Alarm %s: zone '%s' triggered by input %s (event: %s)",
                self._id, zone.name, input_id, event_type,
            )

            if zone.entry_delay:
                self._enter_pending(zone.name, input_id)
            else:
                asyncio.ensure_future(self._trigger(zone.name, input_id))
            return

    # -- State machine -------------------------------------------------------

    async def _arm(self, target_mode: str) -> None:
        """Start arming sequence.

        Args:
            target_mode: The target armed state (armed_home, armed_away, armed_night).
        """
        self._cancel_all_timers()
        self._pending_arm_mode = target_mode

        if self._arming_time_s > 0:
            self._state = ARMING
            self._publish_state()
            _LOGGER.info("Alarm %s arming → %s in %.0fs",
                          self._id, target_mode, self._arming_time_s)

            loop = asyncio.get_running_loop()
            self._arming_timer = loop.call_later(
                self._arming_time_s,
                lambda: asyncio.ensure_future(self._complete_arming()),
            )
        else:
            await self._complete_arming()

    async def _complete_arming(self) -> None:
        """Transition from arming to armed state."""
        if self._pending_arm_mode:
            self._state = self._pending_arm_mode
            self._pending_arm_mode = None
            _LOGGER.info("Alarm %s armed: %s", self._id, self._state)
            self._publish_state()

    async def _disarm(self) -> None:
        """Disarm the alarm, cancel all timers, turn off outputs."""
        self._cancel_all_timers()
        self._state = DISARMED
        self._pending_arm_mode = None
        self._triggered_zone = None
        self._triggered_input = None

        await self._deactivate_outputs()
        self._publish_state()
        _LOGGER.info("Alarm %s disarmed", self._id)

    def _enter_pending(self, zone_name: str, input_id: str) -> None:
        """Enter pending state (entry delay).

        Args:
            zone_name: Name of the zone that triggered.
            input_id: ID of the input that triggered.
        """
        self._state = PENDING
        self._triggered_zone = zone_name
        self._triggered_input = input_id
        self._publish_state()

        _LOGGER.info("Alarm %s pending (entry delay %.0fs) — zone '%s', input %s",
                      self._id, self._delay_time_s, zone_name, input_id)

        loop = asyncio.get_running_loop()
        self._delay_timer = loop.call_later(
            self._delay_time_s,
            lambda: asyncio.ensure_future(
                self._trigger(zone_name, input_id)
            ),
        )

    async def _trigger(self, zone_name: str, input_id: str) -> None:
        """Trigger the alarm — activate outputs.

        Args:
            zone_name: Name of the zone that triggered.
            input_id: ID of the input that triggered.
        """
        self._cancel_all_timers()
        self._state = TRIGGERED
        self._triggered_zone = zone_name
        self._triggered_input = input_id
        self._publish_state()

        _LOGGER.warning("Alarm %s TRIGGERED by zone '%s' input %s",
                         self._id, zone_name, input_id)

        await self._activate_outputs()

        # Auto-disarm after trigger_time
        if self._trigger_time_s > 0:
            loop = asyncio.get_running_loop()
            self._trigger_timer = loop.call_later(
                self._trigger_time_s,
                lambda: asyncio.ensure_future(self._disarm()),
            )

    # -- Output control ------------------------------------------------------

    async def _activate_outputs(self) -> None:
        """Turn on all alarm outputs (siren, notification, etc.)."""
        for alarm_output in self._outputs:
            try:
                await alarm_output.output.async_turn_on()
                _LOGGER.info("Alarm output %s (%s) activated",
                              alarm_output.output.id, alarm_output.output_type)
            except Exception as err:
                _LOGGER.error("Failed to activate alarm output %s: %s",
                               alarm_output.output.id, err)

    async def _deactivate_outputs(self) -> None:
        """Turn off all alarm outputs."""
        for alarm_output in self._outputs:
            try:
                await alarm_output.output.async_turn_off()
                _LOGGER.debug("Alarm output %s (%s) deactivated",
                               alarm_output.output.id, alarm_output.output_type)
            except Exception as err:
                _LOGGER.error("Failed to deactivate alarm output %s: %s",
                               alarm_output.output.id, err)

    # -- Timer management ----------------------------------------------------

    def _cancel_all_timers(self) -> None:
        """Cancel all active timers."""
        for timer in (self._arming_timer, self._delay_timer, self._trigger_timer):
            if timer is not None:
                timer.cancel()
        self._arming_timer = None
        self._delay_timer = None
        self._trigger_timer = None

    # -- MQTT state publishing -----------------------------------------------

    def _publish_state(self) -> None:
        """Publish current alarm state to MQTT."""
        self._message_bus.send_message(
            topic=self._state_topic,
            payload=self._state,
            retain=True,
        )

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start MQTT command subscription."""
        await self._message_bus.subscribe_and_listen(
            self._cmd_topic, self.handle_command
        )
        self._publish_state()
        _LOGGER.info("Alarm panel %s started", self._id)

    async def stop(self) -> None:
        """Stop alarm panel — cancel timers and unsubscribe."""
        self._cancel_all_timers()
        await self._deactivate_outputs()
        try:
            await self._message_bus.unsubscribe_and_stop_listen(self._cmd_topic)
        except Exception:
            pass
        _LOGGER.info("Alarm panel %s stopped", self._id)
