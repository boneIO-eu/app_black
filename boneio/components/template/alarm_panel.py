"""BoneIO Alarm Control Panel — zone-based alarm system.

Monitors input zones, manages arm/disarm state machine with timers,
and controls output devices (siren, notification, etc.) on trigger.

Exposed to Home Assistant as ``alarm_control_panel`` entity via MQTT
autodiscovery.  Code validation is delegated to HA (``REMOTE_CODE``).
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from boneio.const import ALARM_CONTROL_PANEL, STATE

if TYPE_CHECKING:
    from boneio.components.output.basic import BasicOutput
    from boneio.core.events.bus import EventBus
    from boneio.core.manager.inputs import InputManager
    from boneio.core.messaging.basic import MessageBus
    from boneio.core.state.manager import StateManager

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

# Input wiring types
NORMALLY_CLOSED = "normally_closed"
NORMALLY_OPEN = "normally_open"


class ZoneInput:
    """A single input within an alarm zone with wiring type.

    Args:
        input_id: Input entity ID to monitor.
        wiring: Wiring type — 'normally_closed' (default) or 'normally_open'.
            - normally_closed (NC): contact sensor, door, gate — closed circuit = safe,
              open circuit = alarm.  GPIO _state=True means closed (safe).
            - normally_open (NO): PIR motion sensor — open circuit = safe,
              closed circuit = alarm.  GPIO _state=True means closed (alarm).
        source: 'local' (default) for GPIO inputs, 'remote' for inputs from remote devices.
        on_disconnect: Behavior when remote device loses connection.
            'ignore' (default) — skip this sensor, 'trigger' — treat as alarm trigger.
    """

    def __init__(
        self,
        input_id: str,
        wiring: str = NORMALLY_CLOSED,
        source: str = "local",
        on_disconnect: str = "ignore",
    ) -> None:
        self.input_id = input_id
        self.wiring = wiring
        self.source = source
        self.on_disconnect = on_disconnect

    @property
    def is_remote(self) -> bool:
        """Check if this input is from a remote device."""
        return self.source == "remote"

    def is_triggered(self, gpio_state: bool) -> bool:
        """Check if this input is in alarm-triggering state.

        Args:
            gpio_state: Raw GPIO state (True = pressed/closed circuit).

        Returns:
            True if the input should trigger the alarm.
        """
        if self.wiring == NORMALLY_CLOSED:
            # NC: closed = safe, open = alarm → trigger when NOT pressed
            return not gpio_state
        else:
            # NO: open = safe, closed = alarm → trigger when pressed
            return gpio_state


class AlarmZone:
    """A zone groups inputs and defines which arm modes activate them.

    Args:
        name: Human-readable zone name.
        inputs: List of ZoneInput objects to monitor.
        arm_modes: List of arm modes where this zone is active.
        entry_delay: Whether this zone uses entry delay before triggering.
    """

    def __init__(
        self,
        name: str,
        inputs: list[ZoneInput],
        arm_modes: list[str],
        entry_delay: bool = False,
    ) -> None:
        self.name = name
        self.inputs = inputs
        self.input_ids = [zi.input_id for zi in inputs]
        self.arm_modes = arm_modes
        self.entry_delay = entry_delay

    def get_zone_input(self, input_id: str) -> ZoneInput | None:
        """Get ZoneInput by input_id.

        Args:
            input_id: Input entity ID.

        Returns:
            ZoneInput or None if not found.
        """
        for zi in self.inputs:
            if zi.input_id == input_id:
                return zi
        return None

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

    def __init__(self, output: BasicOutput, output_type: str = OUTPUT_SIREN) -> None:
        self.output = output
        self.output_type = output_type


class AlarmPinCode:
    """A named PIN code for alarm arming/disarming.

    Stores the code as a SHA-256 hex digest so plain-text PINs are never
    kept in memory or written to YAML.  If the supplied *code_or_hash* is
    shorter than 64 hex characters it is treated as a plain-text PIN and
    hashed automatically.

    Args:
        name: User name (used in logs to identify who armed/disarmed).
        code_or_hash: Plain-text PIN **or** pre-computed SHA-256 hex digest.
    """

    def __init__(self, name: str, code_or_hash: str) -> None:
        self.name = name
        if self._is_sha256(code_or_hash):
            self._hash = code_or_hash
        else:
            self._hash = self.hash_code(code_or_hash)

    @property
    def code_hash(self) -> str:
        """Return the stored SHA-256 hex digest."""
        return self._hash

    def verify(self, plain_code: str) -> bool:
        """Check a plain-text PIN against the stored hash.

        Args:
            plain_code: The PIN entered by the user.

        Returns:
            True if the PIN matches.
        """
        return self._hash == self.hash_code(plain_code)

    @staticmethod
    def hash_code(plain: str) -> str:
        """Compute SHA-256 hex digest of a plain-text PIN.

        Args:
            plain: Plain-text PIN string.

        Returns:
            64-character lowercase hex digest.
        """
        return hashlib.sha256(plain.encode()).hexdigest()

    @staticmethod
    def _is_sha256(value: str) -> bool:
        """Check whether *value* looks like a SHA-256 hex digest."""
        return len(value) == 64 and all(c in '0123456789abcdef' for c in value.lower())


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
        input_manager: InputManager for checking input states before arming.
        codes: List of AlarmPinCode for multi-user PIN authentication.
        code_arm_required: Whether a code is required to arm (not just disarm).
        allow_frontend_control: Whether the boneIO frontend can arm/disarm.
        arming_time_s: Seconds to wait in arming state before armed.
        delay_time_s: Seconds to wait in pending state before triggered.
        trigger_time_s: Seconds the alarm stays triggered before auto-disarm.
        area: Optional area ID for HA sub-device.
    """

    def __init__(
        self,
        id: str,
        name: str,
        message_bus: MessageBus,
        event_bus: EventBus,
        topic_prefix: str,
        zones: list[AlarmZone],
        outputs: list[AlarmOutput],
        input_manager: InputManager | None = None,
        codes: list[AlarmPinCode] | None = None,
        code_arm_required: bool = False,
        allow_frontend_control: bool = False,
        arming_time_s: float = 30.0,
        delay_time_s: float = 30.0,
        trigger_time_s: float = 300.0,
        area: str | None = None,
        state_manager: StateManager | None = None,
    ) -> None:
        self._id = id
        self._name = name
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._topic_prefix = topic_prefix
        self._zones = zones
        self._outputs = outputs
        self._input_manager = input_manager
        self._codes = codes or []
        self._code_arm_required = code_arm_required
        self._allow_frontend_control = allow_frontend_control
        self._arming_time_s = arming_time_s
        self._delay_time_s = delay_time_s
        self._trigger_time_s = trigger_time_s
        self._area = area
        self._state_manager = state_manager

        # State — restore from persisted state if available
        restored = self._restore_state()
        self._state = restored or DISARMED
        self._pending_arm_mode: str | None = None
        self._arming_started_at: float | None = None

        # Timers
        self._arming_timer: asyncio.TimerHandle | None = None
        self._delay_timer: asyncio.TimerHandle | None = None
        self._trigger_timer: asyncio.TimerHandle | None = None

        # MQTT topics
        self._state_topic = f"{topic_prefix}/alarm/{id}/{STATE}"
        self._cmd_topic = f"{topic_prefix}/cmd/alarm/{id}/set"
        self._attributes_topic = f"{topic_prefix}/alarm/{id}/attributes"

        # Track triggered inputs for logging
        self._triggered_zone: str | None = None
        self._triggered_input: str | None = None

        _LOGGER.info(
            "Initialized BoneIOAlarmPanel: id=%s, zones=%d, outputs=%d, "
            "codes=%d, arming=%.0fs, delay=%.0fs, trigger=%.0fs",
            id, len(zones), len(outputs), len(self._codes),
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

    @property
    def codes(self) -> list[AlarmPinCode]:
        """Get configured PIN codes."""
        return self._codes

    @property
    def code_arm_required(self) -> bool:
        """Whether a code is required to arm the alarm."""
        return self._code_arm_required

    @property
    def allow_frontend_control(self) -> bool:
        """Whether the boneIO frontend is allowed to arm/disarm this alarm."""
        return self._allow_frontend_control

    @property
    def arming_remaining_s(self) -> float | None:
        """Seconds remaining until arming completes, or None if not arming."""
        if self._state != ARMING or self._arming_started_at is None:
            return None
        elapsed = time.monotonic() - self._arming_started_at
        remaining = self._arming_time_s - elapsed
        return max(0.0, round(remaining, 1))

    # -- State persistence ----------------------------------------------------

    _PERSIST_ATTR_TYPE = ALARM_CONTROL_PANEL

    # Only these stable states are worth persisting (not transient arming/pending/triggered)
    _PERSISTABLE_STATES = {DISARMED, ARMED_HOME, ARMED_AWAY, ARMED_NIGHT}

    def _persist_state(self) -> None:
        """Save current alarm state to disk via StateManager."""
        if self._state_manager is None:
            return
        if self._state in self._PERSISTABLE_STATES:
            self._state_manager.save_attribute(
                attr_type=self._PERSIST_ATTR_TYPE,
                attribute=self._id,
                value=self._state,
            )

    def _restore_state(self) -> str | None:
        """Restore alarm state from disk.

        Returns:
            Persisted state string or None if nothing saved.
        """
        if self._state_manager is None:
            return None
        restored = self._state_manager.get(
            attr_type=self._PERSIST_ATTR_TYPE,
            attr=self._id,
        )
        if restored and restored in self._PERSISTABLE_STATES:
            _LOGGER.info("Alarm %s: restored state '%s' from disk", self._id, restored)
            return restored
        return None

    # -- PIN code validation -------------------------------------------------

    def _validate_code(self, code: str | None, action: str) -> tuple[bool, str | None]:
        """Validate a PIN code against configured codes.

        Args:
            code: The PIN code to validate (None if not provided).
            action: The action being performed (for logging).

        Returns:
            Tuple of (is_valid, user_name). If no codes are configured,
            always returns (True, None).
        """
        if not self._codes:
            return True, None

        if not code:
            _LOGGER.warning("Alarm %s: %s rejected — no code provided", self._id, action)
            return False, None

        for pin in self._codes:
            if pin.verify(code):
                return True, pin.name

        _LOGGER.warning("Alarm %s: %s rejected — invalid code", self._id, action)
        return False, None

    # -- MQTT command handler ------------------------------------------------

    async def handle_command(self, _topic: str, payload: str) -> None:
        """Handle alarm command from HA.

        Payload can be a plain command string (ARM_HOME, DISARM, etc.)
        or a JSON object with 'action' and optional 'code' fields:
        {"action": "DISARM", "code": "1234"}

        Args:
            _topic: MQTT topic (unused).
            payload: Command string or JSON payload.
        """
        code: str | None = None
        command: str

        # Try to parse as JSON first (HA sends JSON with code)
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                command = str(data.get("action", data.get("command", ""))).strip().upper()
                code = data.get("code")
            else:
                command = payload.strip().upper()
        except (json.JSONDecodeError, ValueError):
            command = payload.strip().upper()

        _LOGGER.info("Alarm %s received command: %s (current state: %s)",
                      self._id, command, self._state)

        if command == CMD_DISARM:
            valid, user_name = self._validate_code(code, "DISARM")
            if not valid:
                return
            if user_name:
                _LOGGER.info("Alarm %s disarmed by %s", self._id, user_name)
            await self._disarm()
        elif command in (CMD_ARM_HOME, CMD_ARM_AWAY, CMD_ARM_NIGHT):
            if self._code_arm_required:
                valid, user_name = self._validate_code(code, command)
                if not valid:
                    return
                if user_name:
                    _LOGGER.info("Alarm %s armed (%s) by %s", self._id, command, user_name)
            target = {
                CMD_ARM_HOME: ARMED_HOME,
                CMD_ARM_AWAY: ARMED_AWAY,
                CMD_ARM_NIGHT: ARMED_NIGHT,
            }[command]
            await self._arm(target)
        elif command == CMD_TRIGGER:
            await self._trigger("manual", "manual")
        else:
            _LOGGER.warning("Unknown alarm command: %s", command)

    # -- Input event handler -------------------------------------------------

    def on_input_event(self, input_id: str, event_type: str) -> None:
        """Handle input sensor event (pressed/released).

        Called by TemplateManager when a monitored input fires.
        Checks the ZoneInput wiring type to determine if this event
        should trigger the alarm.

        Args:
            input_id: The input entity ID that fired.
            event_type: Event type (e.g. 'pressed', 'released').
        """
        if self._state == DISARMED:
            return

        if self._state in (ARMING, PENDING, TRIGGERED):
            return

        # Determine GPIO state from event_type
        gpio_state = event_type.lower() in ("pressed", "single", "double", "long")

        # Check if any active zone contains this input and if it triggers
        for zone in self._zones:
            zone_input = zone.get_zone_input(input_id)
            if zone_input is None:
                continue
            if not zone.is_active_in_mode(self._state):
                continue
            if not zone_input.is_triggered(gpio_state):
                continue

            _LOGGER.warning(
                "Alarm %s: zone '%s' triggered by input %s "
                "(event: %s, wiring: %s)",
                self._id, zone.name, input_id, event_type,
                zone_input.wiring,
            )

            if zone.entry_delay:
                self._enter_pending(zone.name, input_id)
            else:
                asyncio.ensure_future(self._trigger(zone.name, input_id))
            return

    # -- State machine -------------------------------------------------------

    def _check_zones_clear(self, target_mode: str) -> list[dict[str, str]]:
        """Check if all inputs in zones active for target_mode are safe.

        Reads live GPIO state (not cached _state) for local inputs.
        For remote inputs, uses cached _state and checks device connectivity.
        Uses ZoneInput.is_triggered() to respect NC/NO wiring type.

        Args:
            target_mode: The target armed state to check zones for.

        Returns:
            List of dicts with 'zone', 'input_id', 'input_name', 'wiring'
            for each input in alarm-triggering state.  Empty list means clear.
        """
        from boneio.hardware.gpio.input import get_gpio_manager

        blocking: list[dict[str, str]] = []
        if self._input_manager is None:
            return blocking

        gpio_manager = get_gpio_manager(loop=asyncio.get_event_loop())
        all_inputs = self._input_manager.get_all_inputs()
        for zone in self._zones:
            if not zone.is_active_in_mode(target_mode):
                continue
            for zone_input in zone.inputs:
                inp = all_inputs.get(zone_input.input_id)

                if zone_input.is_remote:
                    # Remote input — check connectivity and cached state
                    if inp is None:
                        # Remote input not registered at all
                        if zone_input.on_disconnect == "trigger":
                            blocking.append({
                                "zone": zone.name,
                                "input_id": zone_input.input_id,
                                "input_name": zone_input.input_id,
                                "wiring": zone_input.wiring,
                            })
                            _LOGGER.warning(
                                "Alarm %s: remote input %s not found, on_disconnect=trigger → blocking",
                                self._id, zone_input.input_id,
                            )
                        else:
                            _LOGGER.debug(
                                "Alarm %s: remote input %s not found, on_disconnect=ignore → skipping",
                                self._id, zone_input.input_id,
                            )
                        continue
                    # Use cached _state for remote (no GPIO)
                    gpio_state = getattr(inp, "_state", False)
                    if zone_input.is_triggered(gpio_state):
                        blocking.append({
                            "zone": zone.name,
                            "input_id": zone_input.input_id,
                            "input_name": getattr(inp, "_name", zone_input.input_id),
                            "wiring": zone_input.wiring,
                        })
                else:
                    # Local GPIO input
                    if inp is None:
                        continue
                    # Read live GPIO state instead of cached _state
                    pin = getattr(inp, "_pin", None)
                    inverted = getattr(inp, "_inverted", False)
                    if pin is not None:
                        raw_value = gpio_manager.read_value(pin)
                        gpio_state = not raw_value if not inverted else raw_value
                    else:
                        gpio_state = getattr(inp, "_state", False)
                    if zone_input.is_triggered(gpio_state):
                        blocking.append({
                            "zone": zone.name,
                            "input_id": zone_input.input_id,
                            "input_name": getattr(inp, "_name", zone_input.input_id),
                            "wiring": zone_input.wiring,
                        })
        return blocking

    async def _arm(self, target_mode: str) -> None:
        """Start arming sequence.

        Refuses to arm if any monitored input is currently active (open)
        and publishes the list of blocking inputs to MQTT.

        Args:
            target_mode: The target armed state (armed_home, armed_away, armed_night).
        """
        blocking = self._check_zones_clear(target_mode)
        if blocking:
            names = ", ".join(
                f"{b['input_name']} ({b['zone']})" for b in blocking
            )
            _LOGGER.warning(
                "Alarm %s: arming to %s blocked by active inputs: %s",
                self._id, target_mode, names,
            )
            # Publish blocking inputs as HA entity attributes
            self._publish_attributes(blocking_inputs=blocking)
            # Stay in current state (disarmed) — do not arm
            return

        # Clear any previous blocking info
        self._publish_attributes(blocking_inputs=[])

        self._cancel_all_timers()
        self._pending_arm_mode = target_mode

        if self._arming_time_s > 0:
            self._state = ARMING
            self._arming_started_at = time.monotonic()
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
            self._arming_started_at = None
            _LOGGER.info("Alarm %s armed: %s", self._id, self._state)
            self._publish_state()
            self._persist_state()

    async def _disarm(self) -> None:
        """Disarm the alarm, cancel all timers, turn off outputs."""
        self._cancel_all_timers()
        self._state = DISARMED
        self._pending_arm_mode = None
        self._arming_started_at = None
        self._triggered_zone = None
        self._triggered_input = None

        await self._deactivate_outputs()
        self._publish_state()
        self._persist_state()
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
        self._publish_attributes()

    def _publish_attributes(
        self, blocking_inputs: list[dict[str, str]] | None = None,
    ) -> None:
        """Publish JSON attributes to MQTT for HA json_attributes_topic.

        Args:
            blocking_inputs: List of inputs blocking arming (optional override).
        """
        attrs: dict[str, Any] = {
            "triggered_zone": self._triggered_zone,
            "triggered_input": self._triggered_input,
        }
        if blocking_inputs is not None:
            attrs["blocking_inputs"] = blocking_inputs
        self._message_bus.send_message(
            topic=self._attributes_topic,
            payload=json.dumps(attrs),
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
        with contextlib.suppress(Exception):
            await self._message_bus.unsubscribe_and_stop_listen(self._cmd_topic)
        _LOGGER.info("Alarm panel %s stopped", self._id)
