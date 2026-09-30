"""Retained replays reach the listeners that asked to tell them apart.

Binary sensor topics are retained (issue #70), so a peer mirroring one gets the
stored copy on every subscribe — every reconnect. Taken as a live change it
ran the input's actions each time the broker came back. The broker marks a
replay with the retain flag; this checks the flag gets through, and only to
listeners that registered for it.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("aiomqtt", reason="aiomqtt not installed in test environment")

from aiomqtt import Topic  # noqa: E402

from boneio.core.messaging.mqtt import MQTTClient  # noqa: E402


@pytest.fixture
def config_helper():
    helper = MagicMock()
    helper.ha_discovery = False
    helper.ha_discovery_prefix = "homeassistant"
    helper.ha_types = []
    helper.serial_number = "0123456789"
    helper.subscribe_topic = "boneio/cmd/#"
    helper.topic_prefix = "boneio"
    helper.receive_boneio_autodiscovery = False
    return helper


@pytest.fixture
async def client(config_helper):
    return MQTTClient(host="localhost", config_helper=config_helper, port=1883)


async def _messages(*items):
    for topic, payload, retain in items:
        yield SimpleNamespace(topic=Topic(topic), payload=payload, retain=retain)


async def _unused(topic, payload):
    raise AssertionError("a listener's message went to the manager callback")


async def test_a_retain_aware_listener_is_told_which_messages_are_replays(client):
    received = []

    async def listener(topic, payload, retained=False):
        received.append((payload, retained))

    await client.subscribe_and_listen("peer/input/in_01", listener, retain_aware=True)
    await client.handle_messages(
        _messages(
            ("peer/input/in_01", b"pressed", True),
            ("peer/input/in_01", b"released", False),
        ),
        _unused,
    )

    assert received == [("pressed", True), ("released", False)]


async def test_other_listeners_keep_the_two_argument_call(client):
    received = []

    async def listener(topic, payload):
        received.append(payload)

    await client.subscribe_and_listen("some/topic", listener)
    await client.handle_messages(_messages(("some/topic", b"42", True)), _unused)

    assert received == ["42"]


async def test_re_registering_without_the_flag_drops_it(client):
    received = []

    async def listener(topic, payload):
        received.append(payload)

    await client.subscribe_and_listen("peer/input/in_01", listener, retain_aware=True)
    await client.subscribe_and_listen("peer/input/in_01", listener)
    await client.handle_messages(_messages(("peer/input/in_01", b"pressed", True)), _unused)

    assert received == ["pressed"]
