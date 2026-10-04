"""A remote output backed by an MQTT device publishes through the message bus."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

sys.modules.setdefault("gpiod", MagicMock())
sys.modules.setdefault("gpiod.line", MagicMock())

from boneio.components.output.remote import RemoteOutputBase
from boneio.core.remote.mqtt import MQTTRemoteDevice


async def test_turn_on_and_off_publish_via_message_bus() -> None:
    message_bus = MagicMock()
    output = RemoteOutputBase(
        id="blk000000_OUT_20",
        name="Out 20",
        device_id="blk000000",
        output_id="OUT_20",
        remote_source="mqtt",
        event_bus=MagicMock(),
        message_bus=message_bus,
        output_type="switch",
    )
    output._device_manager = MQTTRemoteDevice(id="blk000000", name="Remote")

    assert await output.async_turn_on() is True
    await output.async_turn_off()

    topics = [c.kwargs["topic"] for c in message_bus.send_message.call_args_list]
    payloads = [c.kwargs["payload"] for c in message_bus.send_message.call_args_list]
    assert topics == ["boneio/blk000000/cmd/output/OUT_20/set"] * 2
    assert payloads == ["ON", "OFF"]
