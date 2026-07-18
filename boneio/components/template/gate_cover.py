"""BoneIO Gate Cover — impulse-based gate/garage/barrier/wicket control.

Sends short relay pulses to open/close/stop a gate and reads state from
contact sensors (binary_sensor inputs).

State logic depends on which contact sensors are configured:

  Both sensors (closed_sensor + open_sensor):
    - ``closed_sensor`` active   → ``closed``
    - ``closed_sensor`` released → ``opening``
    - ``open_sensor`` active     → ``open``
    - ``open_sensor`` released   → ``closing``
    - Commands only pulse relay, state comes from sensors.

  Only closed_sensor (no open_sensor):
    - ``closed_sensor`` active   → ``closed``
    - ``closed_sensor`` released → ``open``
    - No intermediate states (opening/closing) — we don't know if gate is
      moving or standing still.

  No sensors:
    - State set directly from commands (open/closed).

Exposed to Home Assistant as ``cover`` entity via MQTT autodiscovery.

Control modes:
  - ``cycle``: single button — open→stop→close→stop (most common for gates)
  - ``separate``: dedicated open/close/stop outputs
  - ``open_only``: electric lock — each pulse opens, gate closes by itself
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING

from boneio.const import (
    CLOSE,
    CLOSED,
    CLOSING,
    COVER,
    IDLE,
    OPEN,
    OPENING,
    STATE,
    STOP,
)

if TYPE_CHECKING:
    from boneio.components.output.basic import BasicOutput
    from boneio.core.events.bus import EventBus
    from boneio.core.messaging.basic import MessageBus

_LOGGER = logging.getLogger(__name__)

# Control modes
MODE_CYCLE = "cycle"
MODE_SEPARATE = "separate"
MODE_OPEN_ONLY = "open_only"

# Cycle state machine: tracks what the next pulse should do
CYCLE_OPEN = "open"
CYCLE_CLOSE = "close"


class BoneIOGateCover:
    """Impulse-based gate cover with contact sensor feedback.

    Args:
        id: Unique entity identifier.
        name: Human-readable name for HA.
        message_bus: MessageBus for MQTT communication.
        event_bus: EventBus for internal events.
        topic_prefix: MQTT topic prefix.
        control_mode: 'cycle', 'separate', or 'open_only'.
        device_class: HA device_class (gate, garage_door, barrier, door).
        pulse_output: Output for cycle/open_only modes.
        open_output: Output for separate mode — open command.
        close_output: Output for separate mode — close command.
        stop_output: Output for separate mode — stop command (optional).
        pulse_duration_ms: Pulse duration in ms (None for open_only = hold until open_sensor).
        closed_sensor_id: Input ID for closed contact sensor (optional).
        open_sensor_id: Input ID for open contact sensor (optional).
        area: Optional area ID for HA.
    """

    def __init__(
        self,
        id: str,
        name: str,
        message_bus: MessageBus,
        event_bus: EventBus,
        topic_prefix: str,
        control_mode: str = MODE_CYCLE,
        device_class: str = "gate",
        pulse_output: BasicOutput | None = None,
        open_output: BasicOutput | None = None,
        close_output: BasicOutput | None = None,
        stop_output: BasicOutput | None = None,
        pulse_duration_ms: int | None = 500,
        closed_sensor_id: str | None = None,
        open_sensor_id: str | None = None,
        area: str | None = None,
    ) -> None:
        self._id = id
        self._name = name
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._topic_prefix = topic_prefix
        self._control_mode = control_mode
        self._device_class = device_class
        self._area = area

        # Outputs
        self._pulse_output = pulse_output
        self._open_output = open_output
        self._close_output = close_output
        self._stop_output = stop_output
        self._pulse_duration_ms = pulse_duration_ms

        # Contact sensors
        self._closed_sensor_id = closed_sensor_id
        self._open_sensor_id = open_sensor_id
        self._has_both_sensors = bool(closed_sensor_id and open_sensor_id)
        self._has_closed_sensor = bool(closed_sensor_id)
        self._has_open_sensor = bool(open_sensor_id)

        # State: open, closed, opening, closing
        self._state = CLOSED
        self._current_operation = IDLE

        # Cycle state machine
        self._cycle_next = CYCLE_OPEN

        # Pulse off timer (for turning relay off after pulse)
        self._pulse_off_timer: asyncio.TimerHandle | None = None

        # MQTT topics
        self._state_topic = f"{topic_prefix}/{COVER}/{id}/{STATE}"
        self._cmd_topic = f"{topic_prefix}/cmd/cover/{id}/set"
        self._attributes_topic = f"{topic_prefix}/{COVER}/{id}/attributes"

        self._loop = asyncio.get_event_loop()

        _LOGGER.info(
            "Initialized BoneIOGateCover: id=%s, mode=%s, device_class=%s, "
            "pulse_duration=%s, closed_sensor=%s, open_sensor=%s",
            id,
            control_mode,
            device_class,
            pulse_duration_ms,
            closed_sensor_id,
            open_sensor_id,
        )

    # -- Properties ----------------------------------------------------------

    @property
    def id(self) -> str:
        """Get gate cover ID."""
        return self._id

    @property
    def name(self) -> str:
        """Get gate cover name."""
        return self._name

    @property
    def area(self) -> str | None:
        """Get area ID."""
        return self._area

    @property
    def device_class(self) -> str:
        """Get HA device_class."""
        return self._device_class

    @property
    def control_mode(self) -> str:
        """Get control mode."""
        return self._control_mode

    @property
    def state(self) -> str:
        """Get current cover state (open/closed/opening/closing)."""
        return self._state

    # -- MQTT ----------------------------------------------------------------

    async def start(self) -> None:
        """Subscribe to MQTT command topic and publish current state.

        Initial sensor state is already set by TemplateManager during
        configuration, so start() just subscribes and publishes.
        """
        await self._message_bus.subscribe_and_listen(self._cmd_topic, self.handle_command)
        self._publish_state()
        _LOGGER.info("GateCover %s started (state=%s), subscribed to %s", self._id, self._state, self._cmd_topic)

    async def stop(self) -> None:
        """Unsubscribe from MQTT and cancel timers."""
        self._cancel_pulse_timer()
        with contextlib.suppress(Exception):
            await self._message_bus.unsubscribe_and_stop_listen(self._cmd_topic)
        _LOGGER.info("GateCover %s stopped", self._id)

    async def handle_command(self, _topic: str, payload: str) -> None:
        """Handle cover command from HA (OPEN, CLOSE, STOP).

        Args:
            _topic: MQTT topic (unused).
            payload: Command string.
        """
        command = payload.strip().upper()
        _LOGGER.info("GateCover %s received command: %s", self._id, command)

        if command == OPEN.upper():
            await self._cmd_open()
        elif command == CLOSE.upper():
            await self._cmd_close()
        elif command == STOP.upper():
            await self._cmd_stop()
        else:
            _LOGGER.warning("GateCover %s: unknown command '%s'", self._id, command)

    # -- Command handlers ----------------------------------------------------

    async def _cmd_open(self) -> None:
        """Handle OPEN command.

        Pulses the relay. State change depends on sensor configuration:
        - With sensors: state will update when sensor fires.
        - Without sensors: set state to open immediately.
        """
        if self._control_mode == MODE_OPEN_ONLY:
            await self._pulse_relay(self._pulse_output)
            if not self._has_closed_sensor:
                self._state = OPEN
                self._publish_state()
            return

        if self._control_mode == MODE_SEPARATE:
            await self._pulse_relay(self._open_output)
            if not self._has_closed_sensor:
                self._state = OPEN
                self._publish_state()
            return

        # MODE_CYCLE
        if self._current_operation == IDLE:
            await self._pulse_relay(self._pulse_output)
            self._cycle_next = CYCLE_CLOSE
            if not self._has_closed_sensor:
                self._state = OPEN
                self._publish_state()
        elif self._current_operation == CLOSING:
            # Gate is closing — stop first, then open on next pulse
            await self._pulse_relay(self._pulse_output)
            self._current_operation = IDLE
            self._cycle_next = CYCLE_OPEN

    async def _cmd_close(self) -> None:
        """Handle CLOSE command.

        Pulses the relay. State change depends on sensor configuration:
        - With sensors: state will update when sensor fires.
        - Without sensors: set state to closed immediately.
        """
        if self._control_mode == MODE_OPEN_ONLY:
            _LOGGER.debug("GateCover %s: CLOSE ignored in open_only mode", self._id)
            return

        if self._control_mode == MODE_SEPARATE:
            await self._pulse_relay(self._close_output)
            if not self._has_closed_sensor:
                self._state = CLOSED
                self._publish_state()
            return

        # MODE_CYCLE
        if self._current_operation == IDLE:
            await self._pulse_relay(self._pulse_output)
            self._cycle_next = CYCLE_OPEN
            if not self._has_closed_sensor:
                self._state = CLOSED
                self._publish_state()
        elif self._current_operation == OPENING:
            # Gate is opening — stop first, then close on next pulse
            await self._pulse_relay(self._pulse_output)
            self._current_operation = IDLE
            self._cycle_next = CYCLE_CLOSE

    async def _cmd_stop(self) -> None:
        """Handle STOP command."""
        if self._control_mode == MODE_OPEN_ONLY:
            _LOGGER.debug("GateCover %s: STOP ignored in open_only mode", self._id)
            return

        if self._control_mode == MODE_SEPARATE:
            if self._stop_output:
                await self._pulse_relay(self._stop_output)
            self._current_operation = IDLE
            return

        # MODE_CYCLE — send pulse to stop if moving
        if self._current_operation != IDLE:
            prev_op = self._current_operation
            await self._pulse_relay(self._pulse_output)
            self._current_operation = IDLE
            # After stopping, next pulse should go opposite direction
            if prev_op == OPENING:
                self._cycle_next = CYCLE_CLOSE
            else:
                self._cycle_next = CYCLE_OPEN

    # -- Relay pulse ---------------------------------------------------------

    async def _pulse_relay(self, output: BasicOutput | None) -> None:
        """Send a pulse to a relay output.

        Turns the relay on, then schedules turn-off after pulse_duration_ms.
        For open_only without pulse_duration, relay stays on until open_sensor
        detects the door was opened.

        Args:
            output: The relay output to pulse.
        """
        if output is None:
            _LOGGER.error("GateCover %s: no output configured for pulse", self._id)
            return

        self._cancel_pulse_timer()

        _LOGGER.debug("GateCover %s: pulsing output %s", self._id, output.id)
        await output.async_turn_on()

        if self._pulse_duration_ms is not None:
            delay_s = self._pulse_duration_ms / 1000.0
            self._pulse_off_timer = self._loop.call_later(
                delay_s,
                lambda: asyncio.ensure_future(self._relay_off(output)),
            )
        elif self._control_mode == MODE_OPEN_ONLY:
            _LOGGER.debug("GateCover %s: relay held on until open_sensor triggers", self._id)
        else:
            _LOGGER.warning("GateCover %s: no pulse_duration, turning off immediately", self._id)
            await output.async_turn_off()

    async def _relay_off(self, output: BasicOutput) -> None:
        """Turn off relay after pulse.

        Args:
            output: The relay output to turn off.
        """
        _LOGGER.debug("GateCover %s: turning off output %s", self._id, output.id)
        await output.async_turn_off()
        self._pulse_off_timer = None

    def _cancel_pulse_timer(self) -> None:
        """Cancel pending pulse-off timer."""
        if self._pulse_off_timer is not None:
            self._pulse_off_timer.cancel()
            self._pulse_off_timer = None

    # -- Contact sensor events -----------------------------------------------

    def on_sensor_event(self, sensor_id: str, is_closed: bool) -> None:
        """Handle contact sensor state change.

        Called by TemplateManager when a monitored binary_sensor fires.
        Contact sensor state always takes priority over command-based state.

        With both sensors: use opening/closing intermediate states.
        With only closed_sensor: use closed/open (no intermediate states).

        Args:
            sensor_id: The input entity ID.
            is_closed: True if the contact is closed (GPIO pressed).
        """
        _LOGGER.debug("GateCover %s: sensor %s state=%s", self._id, sensor_id, is_closed)

        if sensor_id == self._closed_sensor_id:
            if is_closed:
                # Closed sensor activated — gate is fully closed
                self._on_gate_closed()
            else:
                # Closed sensor released — gate left closed position
                if self._has_both_sensors:
                    self._current_operation = OPENING
                    self._state = OPENING
                else:
                    # Only closed_sensor — no intermediate state
                    self._current_operation = IDLE
                    self._state = OPEN
                self._publish_state()

        elif sensor_id == self._open_sensor_id:
            if is_closed:
                # Open sensor activated — gate is fully open
                self._on_gate_open()
            else:
                # Open sensor released — gate left open position
                self._current_operation = CLOSING
                self._state = CLOSING
                self._publish_state()

    def _on_gate_closed(self) -> None:
        """Gate reached fully closed position (closed_sensor activated)."""
        _LOGGER.info("GateCover %s: gate closed (sensor)", self._id)
        self._current_operation = IDLE
        self._state = CLOSED
        self._cycle_next = CYCLE_OPEN
        self._publish_state()

    def _on_gate_open(self) -> None:
        """Gate reached fully open position (open_sensor activated)."""
        _LOGGER.info("GateCover %s: gate open (sensor)", self._id)
        self._current_operation = IDLE
        self._state = OPEN
        self._cycle_next = CYCLE_CLOSE

        # For open_only without pulse_duration — turn off relay when open detected
        if self._control_mode == MODE_OPEN_ONLY and self._pulse_duration_ms is None and self._pulse_output is not None:
            asyncio.ensure_future(self._relay_off(self._pulse_output))

        self._publish_state()

    # -- State management ----------------------------------------------------

    def _publish_state(self) -> None:
        """Publish current state to MQTT."""
        self._message_bus.send_message(topic=self._state_topic, payload=self._state)
        _LOGGER.debug("GateCover %s: state=%s", self._id, self._state)

    def _publish_attributes(self) -> None:
        """Publish diagnostic attributes to MQTT."""
        attrs = {
            "control_mode": self._control_mode,
            "device_class": self._device_class,
            "current_operation": self._current_operation,
            "closed_sensor": self._closed_sensor_id,
            "open_sensor": self._open_sensor_id,
        }
        self._message_bus.send_message(
            topic=self._attributes_topic,
            payload=json.dumps(attrs),
        )
