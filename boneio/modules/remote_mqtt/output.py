"""MQTTGenericOutput — remote output publishing commands to an arbitrary MQTT topic.

Subclasses :class:`RemoteOutputBase` to remain duck-type compatible with
``OutputManager`` (irrigation, output groups, frontend, etc.). Overrides
the control methods to publish directly via the MQTT bus instead of
delegating to a remote device manager.

State feedback is optional: when ``state_topic`` is configured, the output
subscribes and evaluates ``state_value_template`` on each incoming payload
to keep its local state in sync with the real device.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from boneio.components.output.remote import RemoteOutputBase
from boneio.const import OFF, ON
from boneio.modules.remote_mqtt.template import coerce_bool, evaluate

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class MQTTGenericOutput(RemoteOutputBase):
    """Remote output controlled via raw MQTT publish + optional state feedback."""

    def __init__(
        self,
        *,
        topic: str,
        message_bus: Any,
        command_template: str = "{{ state }}",
        state_topic: str | None = None,
        state_value_template: str = "{{ value }}",
        state_payload_on: str | None = None,
        state_payload_off: str | None = None,
        qos: int = 0,
        retain: bool = False,
        **base_kwargs: Any,
    ) -> None:
        super().__init__(**base_kwargs)
        self._topic = topic
        self._message_bus = message_bus
        self._command_template = command_template
        self._state_topic = state_topic
        self._state_value_template = state_value_template
        self._state_payload_on = state_payload_on
        self._state_payload_off = state_payload_off
        self._qos = qos
        self._retain = retain
        self._state_subscribed = False
        # No remote device manager — we go straight to the bus. Signal
        # that resolution is "done" so async_turn_on/off skips the check.
        self._available = True
        if state_topic:
            # Schedule subscription on the running event loop (manager calls
            # this from within asyncio context during register_remote_outputs).
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._subscribe_state(), name=f"mqtt-output-{self._id}-state")
            except RuntimeError:
                _LOGGER.warning(
                    "MQTTGenericOutput '%s' instantiated outside event loop — "
                    "state feedback subscription deferred",
                    self._id,
                )

    # ------------------------------------------------------------------
    # Control overrides — publish to the bus, skip device manager flow
    # ------------------------------------------------------------------

    def _resolve_device_manager(self) -> bool:
        """We don't use device managers — always 'resolved'."""
        return True

    async def async_turn_on(self, timestamp: float | None = None) -> None:
        await self._publish_state(ON, timestamp)

    async def async_turn_off(self, timestamp: float | None = None) -> None:
        await self._publish_state(OFF, timestamp)

    async def async_set_brightness(self, brightness: int, timestamp: float | None = None) -> None:
        # Brightness for generic MQTT outputs would need a separate channel
        # (e.g. JSON payload). For MVP we treat brightness=0 as OFF and
        # anything else as ON; users wanting real dimming can wire it up
        # via command_template (e.g. `{"state":"{{ state }}","brightness":{{ brightness }}}`).
        await self._publish_state(
            ON if brightness > 0 else OFF,
            timestamp,
            brightness=brightness,
        )

    async def _publish_state(
        self,
        state: str,
        timestamp: float | None = None,
        brightness: int | None = None,
    ) -> None:
        """Render command_template with `state` (and `brightness`) and publish."""
        try:
            payload = evaluate(
                self._command_template,
                # Reuse template engine context: `value` carries the desired state.
                state,
            )
        except ValueError as exc:
            _LOGGER.warning(
                "MQTTGenericOutput '%s' command_template error: %s — skipping publish",
                self._id, exc,
            )
            return

        # Allow the user to additionally reference {{ state }} / {{ brightness }}
        # in the command_template. Re-render with explicit context if those
        # tokens appear in the template string.
        if "{{ state" in self._command_template or "{{ brightness" in self._command_template:
            try:
                from boneio.modules.remote_mqtt.template import _get_env
                tpl = _get_env().from_string(self._command_template)
                payload = tpl.render(
                    state=state,
                    value=state,
                    brightness=brightness if brightness is not None else (255 if state == ON else 0),
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "MQTTGenericOutput '%s' command_template re-render failed: %s",
                    self._id, exc,
                )

        try:
            self._message_bus.send_message(
                topic=self._topic,
                payload=payload,
                retain=self._retain,
                qos=self._qos,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "MQTTGenericOutput '%s' failed to publish to '%s': %s",
                self._id, self._topic, exc,
            )
            return

        # Optimistic local update — if state_topic is configured, the real
        # state will arrive via _on_state_message and override this if needed.
        self._state = state
        self._last_timestamp = timestamp or time.time()
        if brightness is not None:
            self._brightness = brightness
        self._emit_state_event()
        _LOGGER.debug(
            "MQTTGenericOutput '%s' published to '%s': %r",
            self._id, self._topic, payload,
        )

    # ------------------------------------------------------------------
    # State feedback (optional)
    # ------------------------------------------------------------------

    async def _subscribe_state(self) -> None:
        if not self._state_topic:
            return
        try:
            await self._message_bus.subscribe_and_listen(self._state_topic, self._on_state_message)
            self._state_subscribed = True
            _LOGGER.info(
                "MQTTGenericOutput '%s' subscribed to state_topic '%s'",
                self._id, self._state_topic,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "MQTTGenericOutput '%s' failed to subscribe to state_topic '%s': %s",
                self._id, self._state_topic, exc,
            )

    async def _on_state_message(self, topic: str, payload: str) -> None:
        try:
            rendered = evaluate(self._state_value_template, payload)
        except ValueError as exc:
            _LOGGER.warning(
                "MQTTGenericOutput '%s' state_value_template error on %r: %s",
                self._id, payload, exc,
            )
            return
        bool_value = coerce_bool(rendered, self._state_payload_on, self._state_payload_off)
        if bool_value is None:
            _LOGGER.debug(
                "MQTTGenericOutput '%s' state payload %r → %r doesn't coerce to bool",
                self._id, payload, rendered,
            )
            return
        # Reuses base class state-change handler (emits event + dedupes)
        self.on_remote_state_change(bool_value)

    async def unsubscribe(self) -> None:
        if not self._state_subscribed or not self._state_topic:
            return
        try:
            await self._message_bus.unsubscribe_and_stop_listen(self._state_topic)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "MQTTGenericOutput '%s' failed to unsubscribe from state_topic '%s': %s",
                self._id, self._state_topic, exc,
            )
        self._state_subscribed = False


def setup_remote_output(
    *,
    entity_id: str,
    cfg: dict[str, Any],
    manager: "Manager",
    outputs_dict: dict[str, Any],
) -> bool:
    """Build, register a single MQTT remote output. Designed for a 1-3 line
    injection in ``Manager.register_remote_outputs``.

    Returns True on success, False if cfg is invalid.
    """
    topic = cfg.get("topic")
    if not topic:
        _LOGGER.warning(
            "Skipping mqtt remote output '%s': missing required `topic` field",
            entity_id,
        )
        return False

    name = str(cfg.get("name") or entity_id)
    output_type = str(cfg.get("output_type", "switch"))

    mqtt_output = MQTTGenericOutput(
        id=entity_id,
        name=name,
        device_id=cfg.get("device_id", ""),
        output_id=cfg.get("output_id", entity_id),
        remote_source="mqtt",
        event_bus=manager._event_bus,
        output_type=output_type,
        show_in_ha=bool(cfg.get("show_in_ha", False)),
        area=cfg.get("area"),
        on_disconnect=str(cfg.get("on_disconnect", "ignore")),
        topic=topic,
        message_bus=manager.message_bus,
        command_template=cfg.get("command_template", "{{ state }}"),
        state_topic=cfg.get("state_topic"),
        state_value_template=cfg.get("state_value_template", "{{ value }}"),
        state_payload_on=cfg.get("state_payload_on"),
        state_payload_off=cfg.get("state_payload_off"),
        qos=int(cfg.get("qos", 0)),
        retain=bool(cfg.get("retain", False)),
    )

    outputs_dict[entity_id] = mqtt_output

    _LOGGER.info(
        "Registered MQTT remote output '%s' (topic=%s, state_topic=%s, type=%s)",
        entity_id, topic, cfg.get("state_topic", "—"), output_type,
    )
    return True


async def cleanup_remote_outputs(outputs_dict: dict[str, Any]) -> None:
    """Unsubscribe state_topic listeners for every MQTTGenericOutput.

    Called from ``Manager.unregister_remote_outputs`` so state subscriptions
    don't leak across reloads.
    """
    import asyncio
    tasks = [
        v.unsubscribe()
        for v in outputs_dict.values()
        if isinstance(v, MQTTGenericOutput)
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        _LOGGER.info("Unsubscribed %d MQTT remote output state listener(s)", len(tasks))
