"""Base class for all remote (virtual) input components.

``RemoteInputBase`` provides the common foundation shared by every remote
input transport (ESPHome API, CAN bus, etc.).  It is duck-type compatible
with :class:`GpioBaseClass` so that :class:`InputManager` can treat remote
inputs identically to local GPIO inputs.

Subclasses only need to:
1. Accept transport-specific constructor args (host, sensor_id, …).
2. Build the virtual ``pin`` string (e.g. ``esphome:device:sensor``).
3. Implement ``on_remote_state_change(new_state: bool)`` and call
   the helpers provided here (``_handle_binary_state_change`` or
   ``_feed_detector``).
"""

from __future__ import annotations

import asyncio
import logging
import time

from boneio.const import (
    INPUT,
    INPUT_SENSOR,
    PRESSED,
    RELEASED,
    ClickTypes,
)
from boneio.core.events import EventBus
from boneio.models import InputState
from boneio.models.events import InputEvent

_LOGGER = logging.getLogger(__name__)


class RemoteInputBase:
    """Common base class for remote / virtual input components.

    Provides:
    - EventBus integration (press_callback → InputEvent)
    - Action management (get_actions_of_click, set_actions)
    - Optional MultiClickDetector for ``event`` mode
    - Full duck-type interface matching ``GpioBaseClass``

    Args:
        id: Entity identifier used in MQTT topics and actions.
        name: Human-readable display name.
        pin: Virtual pin string for logging / MQTT (e.g. ``esphome:dev:sensor``).
        event_bus: Central event bus for emitting ``InputEvent`` objects.
        actions: Parsed actions dict (keyed by click type).
        mode: ``"binary_sensor"`` (pressed/released) or ``"event"`` (click detection).
        device_class: Optional HA device class.
        area: Optional HA area assignment.
        inverted: If ``True``, swap pressed / released semantics.
        show_in_ha: Whether to publish HA autodiscovery (default ``True``).
        double_click_duration: Double-click window in ms (event mode only).
        long_press_duration: Long-press threshold in ms (event mode only).
        mqtt_sequences: Dict of enabled MQTT sequences.
        sequence_mode: ``"immediate"`` or ``"exclusive"``.
        long_press_mqtt_mode: ``"single"`` or ``"periodic"``.
        enable_triple_click: Enable triple-click detection.
    """

    def __init__(
        self,
        *,
        id: str,
        name: str,
        pin: str,
        event_bus: EventBus,
        actions: dict,
        mode: str = "binary_sensor",
        device_class: str | None = None,
        area: str | None = None,
        inverted: bool = False,
        show_in_ha: bool = True,
        double_click_duration: int = 220,
        long_press_duration: int = 400,
        mqtt_sequences: dict | None = None,
        sequence_mode: str = "exclusive",
        long_press_mqtt_mode: str = "single",
        enable_triple_click: bool = False,
    ) -> None:
        self._id = id
        self._name = name
        self._pin = pin
        self._event_bus = event_bus
        self._actions = actions
        self._mode = mode
        self._device_class = device_class
        self.area: str | None = area
        self._inverted = inverted
        self.show_in_ha = show_in_ha
        self._state = False
        self._last_state = "Unknown"
        self._last_timestamp = 0.0
        self._loop = asyncio.get_running_loop()
        self._event_lock = asyncio.Lock()
        self._boneio_input = ""
        self._mqtt_sequences: dict[str, bool] = mqtt_sequences or {}
        self._sequence_mode = sequence_mode
        self._long_press_mqtt_mode = long_press_mqtt_mode

        # Determine input type based on mode.
        self._input_type = INPUT if mode == "event" else INPUT_SENSOR

        # For event mode, create a MultiClickDetector.
        self._detector = None
        if mode == "event":
            from boneio.components.input.detectors import MultiClickDetector

            enabled_sequences: set[str] = set()
            seq_types = {"double_then_long", "single_then_long", "double_then_single"}
            if isinstance(actions, dict):
                for st in seq_types:
                    if st in actions and actions[st]:
                        enabled_sequences.add(st)
            if isinstance(mqtt_sequences, dict):
                for st in seq_types:
                    if mqtt_sequences.get(st):
                        enabled_sequences.add(st)

            self._detector = MultiClickDetector(
                loop=self._loop,
                callback=self._on_click_detected,
                debounce_ms=20.0,  # short debounce — remote side already debounces
                multiclick_window_ms=float(double_click_duration),
                hold_threshold_ms=float(long_press_duration),
                sequence_mode=sequence_mode,
                enabled_sequences=enabled_sequences,
                enable_triple_click=enable_triple_click,
                name=name,
                pin=pin,
            )

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    def _handle_binary_state_change(self, new_state: bool) -> None:
        """Process a state change in binary_sensor mode.

        Emits ``pressed`` or ``released`` directly to EventBus.
        Should be called by subclass ``on_remote_state_change`` **after**
        applying inversion.

        Args:
            new_state: ``True`` if the sensor is now active/on.
        """
        self._state = new_state
        click_type = PRESSED if new_state else RELEASED
        self.press_callback(click_type=click_type, duration=None, start_time=time.time())

    def _feed_detector(self, is_pressed: bool) -> None:
        """Feed a state change into the MultiClickDetector (event mode).

        Should be called by subclass ``on_remote_state_change`` **after**
        applying inversion.

        Args:
            is_pressed: ``True`` if the input is now active.
        """
        if self._detector is not None:
            self._detector.handle_raw_state(is_pressed=is_pressed)

    # ------------------------------------------------------------------
    # Event mode click callback
    # ------------------------------------------------------------------

    def _on_click_detected(self, click_type: ClickTypes, duration: float | None) -> None:
        """Callback from MultiClickDetector when a click pattern is detected.

        Args:
            click_type: Detected click type (single, double, long …).
            duration: Duration of the press in seconds (for long press).
        """
        _LOGGER.debug(
            "Click detected on remote input %s: %s (duration=%s)",
            self._name, click_type, duration,
        )
        self.press_callback(click_type=click_type, duration=duration, start_time=time.time())

    # ------------------------------------------------------------------
    # press_callback & event emission (same interface as GpioBaseClass)
    # ------------------------------------------------------------------

    def press_callback(
        self,
        click_type: ClickTypes,
        duration: float | None = None,
        start_time: float | None = None,
    ) -> None:
        """Schedule async event processing.

        Args:
            click_type: Type of click.
            duration: Duration of the press in seconds.
            start_time: Start time of the press.
        """
        asyncio.create_task(self._handle_press_with_lock(click_type, duration, start_time))

    async def _handle_press_with_lock(
        self,
        click_type: ClickTypes,
        duration: float | None = None,
        start_time: float | None = None,
    ) -> None:
        """Emit InputEvent on EventBus (serialised with lock)."""
        async with self._event_lock:
            self._last_timestamp = time.time()
            self._last_state = click_type

            _LOGGER.debug(
                "Remote input event: %s on %s, entity_id=%s, duration=%s",
                click_type, self._name, self.id, duration,
            )

            event_state = InputState(
                name=self.name,
                pin=self._pin,
                state=self.last_state,
                type=self.input_type,
                timestamp=self.last_press_timestamp,
                boneio_input=self.boneio_input,
                area=self.area,
            )

            self._event_bus.trigger_event(
                InputEvent(
                    entity_id=self.id,
                    click_type=click_type,
                    duration=duration,
                    state=event_state,
                )
            )

    # ------------------------------------------------------------------
    # Interface properties (duck-type compatible with GpioBaseClass)
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
    def pin(self) -> str:
        """Virtual pin identifier."""
        return self._pin

    @property
    def boneio_input(self) -> str:
        """BoneIO input identifier (empty for remote inputs)."""
        return self._boneio_input

    @property
    def input_type(self) -> str:
        """Return ``input`` (event mode) or ``inputsensor`` (binary sensor mode)."""
        return self._input_type

    @property
    def device_class(self) -> str | None:
        """HA device class."""
        return self._device_class

    @property
    def last_state(self) -> str:
        """Last emitted state string."""
        return self._last_state

    @property
    def is_active(self) -> bool:
        """Whether the sensor is currently in the active state."""
        return self._state

    @property
    def last_press_timestamp(self) -> float:
        """Unix timestamp of the last event."""
        return self._last_timestamp

    @property
    def mqtt_sequences(self) -> dict[str, bool]:
        """MQTT sequences configuration."""
        return self._mqtt_sequences

    @property
    def sequence_mode(self) -> str:
        """Sequence mode (``immediate`` or ``exclusive``)."""
        return self._sequence_mode

    @property
    def long_press_mqtt_mode(self) -> str:
        """Long press MQTT mode (``single`` or ``periodic``)."""
        return self._long_press_mqtt_mode

    @property
    def mode(self) -> str:
        """Operating mode (``binary_sensor`` or ``event``)."""
        return self._mode

    def set_actions(self, actions: dict) -> None:
        """Replace configured actions.

        Args:
            actions: New actions dict keyed by click type.
        """
        self._actions = actions

    def get_actions_of_click(self, click_type: ClickTypes) -> list:
        """Return actions for a specific click type.

        Args:
            click_type: Type of click.

        Returns:
            List of action definitions.
        """
        return self._actions.get(click_type, [])

    def should_publish_sequence_to_mqtt(self, sequence_type: ClickTypes | None) -> bool:
        """Check if a sequence type should be published to MQTT.

        Args:
            sequence_type: Sequence name (e.g. ``double_then_long``).

        Returns:
            ``True`` if the sequence should be published.
        """
        if sequence_type is None:
            return False
        return self._mqtt_sequences.get(sequence_type, False)
