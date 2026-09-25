"""One bad message must not take MQTT down.

Anything a client of the broker publishes on a command topic reaches the
manager. An exception on the way — a payload that isn't UTF-8, a brightness
that isn't a number — ended the session, and since it wasn't an MqttError it
ended the client loop with it. Nothing restarts that loop, so the device
stayed off MQTT until the application was restarted.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("aiomqtt", reason="aiomqtt not installed in test environment")

from aiomqtt import Topic  # noqa: E402

from boneio.core.messaging.mqtt import MQTTClient  # noqa: E402


@pytest.fixture
def config_helper():
    """The bits of ConfigHelper the client reads while it is built."""
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
    """A client that has never connected to anything."""
    return MQTTClient(
        host="localhost",
        config_helper=config_helper,
        port=1883,
        username="boneio",
        password="boneio123",
    )


async def _messages(*items):
    for topic, payload in items:
        yield SimpleNamespace(topic=Topic(topic), payload=payload)


async def test_a_payload_that_is_not_utf8_is_dropped(client):
    """The message after it still arrives."""
    received = []

    async def callback(topic, payload):
        received.append((topic, payload))

    await client.handle_messages(
        _messages(
            ("boneio/cmd/relay/out01/set", b"\xff\xfe"),
            ("boneio/cmd/relay/out02/set", b"ON"),
        ),
        callback,
    )

    assert received == [("boneio/cmd/relay/out02/set", "ON")]


async def test_a_failing_handler_does_not_end_the_session(client):
    """int("abc") in set_brightness was the one testers could trigger."""
    received = []

    async def callback(topic, payload):
        if payload == "abc":
            raise ValueError("invalid literal for int()")
        received.append(payload)

    await client.handle_messages(
        _messages(
            ("boneio/cmd/relay/out01/set_brightness", b"abc"),
            ("boneio/cmd/relay/out01/set_brightness", b"50"),
        ),
        callback,
    )

    assert received == ["50"]


async def test_the_client_reconnects_after_an_unexpected_error(client):
    """Only MqttError led to a reconnect; anything else ended the loop."""
    started = asyncio.Event()
    attempts = 0

    async def session(manager):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("not an MqttError")
        started.set()
        await asyncio.Event().wait()

    client._manager = MagicMock()
    client._subscribe_manager = session
    client.reconnect_interval = 0  # backoff doubles it; keep the test instant
    task = asyncio.create_task(client.start_client())
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        assert attempts == 2
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
