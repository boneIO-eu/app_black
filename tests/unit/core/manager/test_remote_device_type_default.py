"""A remote device without device_type keeps the boneio/ prefix after a hot reload.

The schema defaults device_type to boneio_black, but the hot-reload path
(ConfigHelper.reload_config) skips Cerberus normalization, so the manager
sees the raw YAML with the key missing.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

sys.modules.setdefault("gpiod", MagicMock())
sys.modules.setdefault("gpiod.line", MagicMock())

from boneio.core.manager.remote import RemoteDeviceManager


def _raw_config(**extra: str) -> list[dict]:
    return [
        {
            "id": "blkabc123",
            "name": "Peer",
            "protocol": "mqtt",
            "mqtt": {"outputs": [{"id": "o1", "name": "O1"}]},
            **extra,
        }
    ]


async def test_reload_without_device_type_uses_boneio_prefix() -> None:
    message_bus = MagicMock()
    manager = RemoteDeviceManager(message_bus=message_bus, own_serial="blkself01")

    await manager.reload(_raw_config())

    device = manager.get_device("blkabc123")
    assert device.topic_prefix == "boneio/blkabc123"
    assert device._get_output_command_topic("o1") == "boneio/blkabc123/cmd/output/o1/set"
    topics = [c.kwargs["topic"] for c in message_bus.send_message.call_args_list]
    assert topics == ["boneio/blkabc123/discovery/managed_by/blkself01"]


async def test_reload_with_explicit_generic_keeps_bare_prefix() -> None:
    manager = RemoteDeviceManager(message_bus=MagicMock(), own_serial="blkself01")

    await manager.reload(_raw_config(device_type="generic"))

    assert manager.get_device("blkabc123").topic_prefix == "blkabc123"
