"""Adopting new broker credentials without restarting the application.

The credentials are read once, when the client is built. Changing the broker
password therefore took the device off its own broker until somebody edited
config.yaml and restarted — which is what testers reported as the password
change not working.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

pytest.importorskip("aiomqtt", reason="aiomqtt not installed in test environment")

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
    """A client that has never connected to anything.

    Async because building one needs a running loop: aiomqtt captures it.
    """
    return MQTTClient(
        host="localhost",
        config_helper=config_helper,
        port=1883,
        username="boneio",
        password="boneio123",
    )


async def test_the_same_credentials_are_not_a_reconnect(client):
    """Saving an unrelated field must not drop a healthy connection."""
    assert await client.reload_credentials(
        host="localhost", port=1883, username="boneio", password="boneio123"
    ) is False


async def test_a_new_password_is_what_the_next_client_presents(client):
    """The point of the whole exercise."""
    assert await client.reload_credentials(
        host="localhost", port=1883, username="boneio", password="nowe-haslo"
    ) is True
    assert client.client_options["password"] == "nowe-haslo"


async def test_the_next_session_does_not_share_an_identifier(client):
    """A broker drops the older of two connections claiming one identifier,
    and the session being replaced may still be on its way down."""
    before = client.client_options["identifier"]
    await client.reload_credentials(
        host="localhost", port=1883, username="boneio", password="nowe-haslo"
    )
    assert client.client_options["identifier"] != before


async def test_a_new_broker_moves_the_client(client):
    """Host and port travel with the credentials."""
    await client.reload_credentials(
        host="192.168.1.50", port=8883, username="boneio", password="boneio123"
    )
    assert (client.host, client.port) == ("192.168.1.50", 8883)


async def test_nothing_is_interrupted_when_nothing_is_running(client):
    """Between attempts the loop builds its next client from the stored
    options by itself, so there is no session to end."""
    assert await client.reload_credentials(
        host="localhost", port=1883, username="boneio", password="nowe-haslo"
    ) is True
    assert client._reloading is False


async def _running(client) -> tuple[asyncio.Task, asyncio.Queue]:
    """Start the client loop against a session that never ends on its own.

    Args:
        client: The client under test.

    Returns:
        The loop's task, and a queue receiving the client object each session
        was started with.
    """
    started: asyncio.Queue = asyncio.Queue()

    async def never_ends(manager):
        await started.put(client.asyncio_client)
        await asyncio.Event().wait()

    client._manager = MagicMock()
    client._subscribe_manager = never_ends
    task = asyncio.create_task(client.start_client())
    return task, started


async def test_a_reload_starts_a_new_session_with_the_new_client(client):
    """The loop only rebuilt the client after an MqttError. New credentials
    are the second reason it has to."""
    task, started = await _running(client)
    try:
        first = await asyncio.wait_for(started.get(), timeout=2)

        await client.reload_credentials(
            host="localhost", port=1883, username="boneio", password="nowe-haslo"
        )

        second = await asyncio.wait_for(started.get(), timeout=2)
        assert second is not first
        assert client._reloading is False
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_a_cancel_from_outside_still_stops_the_client(client):
    """The reload path catches CancelledError. Shutdown must not be caught
    with it and turned into a reconnect loop that never ends."""
    task, started = await _running(client)
    await asyncio.wait_for(started.get(), timeout=2)

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert task.done()
