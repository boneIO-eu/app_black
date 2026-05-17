"""MQTTGenericInput — remote input subscribing to an arbitrary MQTT topic.

Subscribes to a single topic, runs each incoming payload through a Jinja2
``value_template``, coerces the rendered result to a bool (using optional
``payload_on`` / ``payload_off`` overrides or built-in truthy/falsy
fallbacks), and emits ``InputEvent`` via the standard
:class:`RemoteInputBase` machinery.

Subclasses :class:`RemoteInputBase` to remain duck-type compatible with
``InputManager`` — actions, HA discovery, and event flow work identically
to ESPHome / GPIO inputs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.components.input.remote.base import RemoteInputBase
from boneio.const import EVENT_ENTITY
from boneio.modules.remote_mqtt.template import coerce_bool, evaluate

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class MQTTGenericInput(RemoteInputBase):
    """Subscribe to an MQTT topic and emit input events from rendered template values."""

    def __init__(
        self,
        *,
        topic: str,
        message_bus: Any,
        value_template: str = "{{ value }}",
        payload_on: str | None = None,
        payload_off: str | None = None,
        **base_kwargs: Any,
    ) -> None:
        super().__init__(**base_kwargs)
        self._topic = topic
        self._message_bus = message_bus
        self._value_template = value_template
        self._payload_on = payload_on
        self._payload_off = payload_off
        self._subscribed = False
        self._boneio_input = f"mqtt:{topic}"
        # Subscribe ASAP in the running loop. RemoteInputBase.__init__ has
        # already captured ``self._loop = asyncio.get_running_loop()``.
        self._loop.create_task(self._subscribe(), name=f"mqtt-input-{self._id}-subscribe")

    async def _subscribe(self) -> None:
        try:
            await self._message_bus.subscribe_and_listen(self._topic, self._on_message)
            self._subscribed = True
            _LOGGER.info(
                "MQTTGenericInput '%s' subscribed to topic '%s' (template=%r)",
                self._id, self._topic, self._value_template,
            )
        except Exception as exc:
            _LOGGER.error(
                "MQTTGenericInput '%s' failed to subscribe to '%s': %s",
                self._id, self._topic, exc,
            )

    async def _on_message(self, topic: str, payload: str) -> None:
        """Render template, coerce to bool, dispatch through base helpers."""
        try:
            rendered = evaluate(self._value_template, payload)
        except ValueError as exc:
            _LOGGER.warning(
                "MQTTGenericInput '%s' template error on payload %r: %s",
                self._id, payload, exc,
            )
            return

        bool_value = coerce_bool(rendered, self._payload_on, self._payload_off)
        if bool_value is None:
            _LOGGER.debug(
                "MQTTGenericInput '%s': payload %r → rendered %r doesn't coerce to bool — dropping",
                self._id, payload, rendered,
            )
            return

        if self._inverted:
            bool_value = not bool_value

        if self._mode == "event":
            self._feed_detector(is_pressed=bool_value)
        else:
            # Only emit on transitions — MQTT will republish on every change,
            # but some publishers also republish the same state periodically.
            if bool_value == self._state:
                return
            self._handle_binary_state_change(bool_value)

    async def unsubscribe(self) -> None:
        """Unsubscribe from the broker — called by registrar.unregister_all."""
        if not self._subscribed:
            return
        try:
            await self._message_bus.unsubscribe_and_stop_listen(self._topic)
        except Exception as exc:
            _LOGGER.warning(
                "MQTTGenericInput '%s' failed to unsubscribe from '%s': %s",
                self._id, self._topic, exc,
            )
        self._subscribed = False


def setup_remote_input(
    *,
    custom_id: str,
    cfg: dict[str, Any],
    manager: "Manager",
    inputs_dict: dict[str, Any],
    parsed_actions: dict,
    ha_discovery_fn: Any = None,
) -> bool:
    """Build, register, and (if enabled) HA-discover a single MQTT remote input.

    Designed to be called from ``RemoteInputRegistrar._register_single`` as a
    1-3 line injection. All heavy lifting (parameter mapping, instantiation,
    subscribe, HA discovery) lives here so the upstream file stays minimal.

    Returns True on success, False on validation failure.
    """
    topic = cfg.get("topic")
    if not topic:
        _LOGGER.warning(
            "Skipping mqtt remote input '%s': missing required `topic` field",
            custom_id,
        )
        return False

    name = cfg.get("name") or custom_id
    mode = cfg.get("mode", "binary_sensor")

    mqtt_input = MQTTGenericInput(
        id=custom_id,
        name=name,
        pin=f"mqtt:{topic}",
        topic=topic,
        message_bus=manager.message_bus,
        value_template=cfg.get("value_template", "{{ value }}"),
        payload_on=cfg.get("payload_on"),
        payload_off=cfg.get("payload_off"),
        event_bus=manager._event_bus,
        actions=parsed_actions,
        mode=mode,
        device_class=cfg.get("device_class"),
        area=cfg.get("area"),
        inverted=cfg.get("inverted", False),
        show_in_ha=cfg.get("show_in_ha", False),
        double_click_duration=cfg.get("double_click_duration", 220),
        long_press_duration=cfg.get("long_press_duration", 400),
        mqtt_sequences=cfg.get("mqtt_sequences"),
        sequence_mode=cfg.get("sequence_mode", "exclusive"),
        long_press_mqtt_mode=cfg.get("long_press_mqtt_mode", "single"),
        enable_triple_click=cfg.get("enable_triple_click", False),
    )

    inputs_dict[custom_id] = mqtt_input

    if cfg.get("show_in_ha") and ha_discovery_fn is not None:
        ha_type = EVENT_ENTITY if mode == "event" else "binary_sensor"
        ha_discovery_fn(
            ha_type=ha_type,
            input_id=custom_id,
            name=name,
            device_class=cfg.get("device_class"),
            area=cfg.get("area"),
            mqtt_sequences=cfg.get("mqtt_sequences"),
            enable_triple_click=cfg.get("enable_triple_click", False),
        )

    _LOGGER.info(
        "Registered MQTT remote input '%s' (topic=%s, mode=%s)",
        custom_id, topic, mode,
    )
    return True


async def cleanup_remote_inputs(inputs_dict: dict[str, Any]) -> None:
    """Unsubscribe every MQTTGenericInput in ``inputs_dict``.

    Called from ``RemoteInputRegistrar.unregister_all`` (in cooperation with
    the existing isinstance(RemoteInputBase) cleanup) so MQTT subscriptions
    don't leak across reloads.
    """
    tasks = [
        v.unsubscribe()
        for v in inputs_dict.values()
        if isinstance(v, MQTTGenericInput)
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        _LOGGER.info("Unsubscribed %d MQTT remote input(s)", len(tasks))
