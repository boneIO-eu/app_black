"""MQTT binary sensor input — a remote input carried over MQTT.

The obvious use is mirroring another boneIO: a peer publishes its inputs at
``<its topic prefix>/input/<input id>``, and this subscribes to exactly that,
so a button on one controller can drive a relay on another with nothing in
between but the broker.

It is not limited to boneIO. Anything that publishes an on/off payload on a
topic works — an ESPHome device in MQTT mode, a Zigbee bridge, a script — by
giving the entry an explicit ``topic``.

What it is *not* for: a flag you flip by hand from Home Assistant. That is a
`virtual_switch`, which boneIO owns and persists. This is for mirroring
something that already exists somewhere else.
"""

from __future__ import annotations

import json
import logging

from boneio.components.input.remote.base import RemoteInputBase
from boneio.core.events import EventBus

_LOGGER = logging.getLogger(__name__)

#: Payloads that mean "on". Three vocabularies at once, because the three
#: things people point this at do not agree: boneIO publishes pressed/released,
#: ESPHome publishes ON/OFF, and everything else publishes true/1.
_TRUTHY = frozenset({"on", "true", "1", "pressed", "open", "opening", "active"})
_FALSY = frozenset({"off", "false", "0", "released", "closed", "closing", "inactive"})


class MqttBinarySensorInput(RemoteInputBase):
    """A remote input whose state arrives on an MQTT topic.

    Args:
        device_id: ID of the remote device, from ``remote_devices``.
        sensor_id: The input's id on that device.
        topic: Topic to subscribe to.
        id: Local input id.
        name: Display name.
        event_bus: EventBus.
        actions: Parsed actions, keyed by click type.
        **kwargs: Forwarded to :class:`RemoteInputBase`.
    """

    def __init__(
        self,
        *,
        device_id: str,
        sensor_id: str,
        topic: str,
        id: str,
        name: str,
        event_bus: EventBus,
        actions: dict,
        **kwargs,
    ) -> None:
        self._device_id = device_id
        self._sensor_id = sensor_id
        self._topic = topic

        super().__init__(
            id=id,
            name=name,
            pin=f"mqtt:{device_id}:{sensor_id}",
            event_bus=event_bus,
            actions=actions,
            **kwargs,
        )

        _LOGGER.debug(
            "Created MQTT binary sensor input %s (mode=%s, topic=%s)",
            id,
            self._mode,
            topic,
        )

    @property
    def topic(self) -> str:
        """The topic this input listens on."""
        return self._topic

    @staticmethod
    def parse_state(payload: str) -> bool | None:
        """Read an on/off payload, or None if it is not one.

        Returns:
            True or False, or None when the payload means nothing here — in
            which case the caller leaves the state alone rather than guessing,
            because a wrong guess silently drives a relay.
        """
        text = (payload or "").strip().strip('"').lower()
        if text in _TRUTHY:
            return True
        if text in _FALSY:
            return False
        return None

    async def on_mqtt_message(self, _topic: str, payload: str) -> None:
        """Handle a message on the subscribed topic.

        Two payload shapes are understood. A plain on/off state is the usual
        one. A JSON object with ``event_type`` is what a boneIO *event* input
        publishes — a click that has already been classified — and in event
        mode it is passed through as-is rather than re-derived from a state
        this side never saw.

        Args:
            _topic: The topic it arrived on; unused, one subscription per input.
            payload: The message.
        """
        text = (payload or "").strip()

        if text.startswith("{"):
            try:
                event_type = json.loads(text).get("event_type")
            except ValueError:
                event_type = None
            if event_type:
                if self._mode == "event":
                    self.press_callback(click_type=event_type, duration=None)
                else:
                    _LOGGER.debug(
                        "Input %s got a click event but is in binary_sensor mode; "
                        "set `mode: event` to use it.",
                        self.id,
                    )
                return

        state = self.parse_state(text)
        if state is None:
            _LOGGER.warning(
                "Input %s: cannot read %r as a state. Expected on/off, "
                "true/false, 1/0 or pressed/released.",
                self.id,
                payload,
            )
            return

        if self._inverted:
            state = not state

        if self._mode == "event":
            self._feed_detector(is_pressed=state)
        else:
            self._handle_binary_state_change(state)
