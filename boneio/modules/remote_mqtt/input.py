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
from boneio.modules.remote_mqtt.dispatcher import get_dispatcher
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
            dispatcher = get_dispatcher(self._message_bus)
            await dispatcher.subscribe(self._topic, self._on_message, f"input:{self._id}")
            self._subscribed = True
            _LOGGER.info(
                "MQTTGenericInput '%s' subscribed to topic '%s' (template=%r)",
                self._id, self._topic, self._value_template,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "MQTTGenericInput '%s' failed to subscribe to '%s': %s",
                self._id, self._topic, exc,
            )

    async def _on_message(self, topic: str, payload: str) -> None:
        """Render template, coerce to bool, dispatch through base helpers.

        Verbose INFO logging while we're stabilising the device-centric
        pivot — each step says what happened so failures are diagnosable
        from the journal without a debugger. Demote to DEBUG once stable.
        """
        _LOGGER.info(
            "MQTTGenericInput '%s' RX topic=%s payload=%r",
            self._id, topic, payload,
        )
        try:
            rendered = evaluate(self._value_template, payload)
        except ValueError as exc:
            _LOGGER.warning(
                "MQTTGenericInput '%s' template %r raised on payload %r: %s",
                self._id, self._value_template, payload, exc,
            )
            return

        bool_value = coerce_bool(rendered, self._payload_on, self._payload_off)
        _LOGGER.info(
            "MQTTGenericInput '%s' rendered=%r coerced=%s (payload_on=%r payload_off=%r)",
            self._id, rendered, bool_value, self._payload_on, self._payload_off,
        )
        if bool_value is None:
            _LOGGER.warning(
                "MQTTGenericInput '%s' DROPPED — rendered %r doesn't match payload_on/off and isn't a recognised boolean token",
                self._id, rendered,
            )
            return

        if self._inverted:
            bool_value = not bool_value

        if self._mode == "event":
            self._feed_detector(is_pressed=bool_value)
            return

        # Only emit on transitions — MQTT will republish on every change,
        # but some publishers also republish the same state periodically.
        if bool_value == self._state:
            _LOGGER.info(
                "MQTTGenericInput '%s' no transition (state already %s) — not emitting",
                self._id, bool_value,
            )
            return
        _LOGGER.info(
            "MQTTGenericInput '%s' EMIT transition %s → %s",
            self._id, self._state, bool_value,
        )
        self._handle_binary_state_change(bool_value)

    async def unsubscribe(self) -> None:
        """Unsubscribe from the broker — called by registrar.unregister_all."""
        if not self._subscribed:
            return
        try:
            dispatcher = get_dispatcher(self._message_bus)
            await dispatcher.unsubscribe(self._topic, f"input:{self._id}")
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "MQTTGenericInput '%s' failed to unsubscribe from '%s': %s",
                self._id, self._topic, exc,
            )
        self._subscribed = False


def _find_device_input(manager: "Manager", device_id: str, input_id: str) -> dict | None:
    """Look up the input definition (with topic + template) on the remote device.

    Mirrors the ESPHome pattern: the device declares its entities in
    ``remote_devices[*].mqtt.inputs``, and ``remote_inputs`` rows just
    reference them by ``device_id + input_id``.
    """
    full_cfg = manager._config_helper.get_config()
    devices_cfg = full_cfg.get("remote_devices", [])
    device_cfg = next((d for d in devices_cfg if d.get("id") == device_id), None)
    if not device_cfg:
        return None
    inputs = device_cfg.get("mqtt", {}).get("inputs", [])
    return next((i for i in inputs if i.get("id") == input_id), None)


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

    Resolves the input definition (topic + value_template + payload_on/off)
    by looking up ``cfg.input_id`` on ``cfg.device_id`` in the
    ``remote_devices`` config — exactly like the ESPHome path resolves
    binary_sensor entities. The ``remote_inputs`` row itself only carries
    routing (device_id, input_id, mode, actions, area, etc.).

    Returns True on success, False on validation failure.
    """
    device_id = cfg.get("device_id")
    input_id = cfg.get("input_id")
    if not device_id or not input_id:
        _LOGGER.warning(
            "Skipping mqtt remote input '%s': missing device_id or input_id",
            custom_id,
        )
        return False

    input_def = _find_device_input(manager, device_id, input_id)
    if not input_def:
        _LOGGER.warning(
            "MQTT remote input '%s': input '%s' not found on device '%s' "
            "(remote_devices[%s].mqtt.inputs). Add it on the device first.",
            custom_id, input_id, device_id, device_id,
        )
        return False

    topic = input_def.get("topic")
    if not topic:
        _LOGGER.warning(
            "MQTT remote input '%s': device input '%s/%s' has no `topic` "
            "configured — edit the device's input definition.",
            custom_id, device_id, input_id,
        )
        return False

    # Display name precedence: remote_input override > device input name > custom_id
    name = cfg.get("name") or input_def.get("name") or custom_id
    mode = cfg.get("mode", "binary_sensor")

    mqtt_input = MQTTGenericInput(
        id=custom_id,
        name=name,
        pin=f"mqtt:{topic}",
        topic=topic,
        message_bus=manager.message_bus,
        value_template=input_def.get("value_template", "{{ value }}"),
        payload_on=input_def.get("payload_on"),
        payload_off=input_def.get("payload_off"),
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
        "Registered MQTT remote input '%s' (device=%s/%s, topic=%s, mode=%s)",
        custom_id, device_id, input_id, topic, mode,
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
