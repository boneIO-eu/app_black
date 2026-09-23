"""The glue between a saved mqtt section and the running MQTT client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.core.manager.manager import Manager
from boneio.core.messaging.composite import CompositeMessageBus


@pytest.fixture
def bus():
    """A message bus that answers like the MQTT one, without a broker."""
    client = MagicMock()
    client.host = "localhost"
    client.port = 1883
    client.client_options = {"username": "boneio", "password": "boneio123"}
    client.reload_credentials = AsyncMock(return_value=True)
    return client


@pytest.fixture
def manager(bus):
    """Enough of a Manager to run the reload, and nothing more."""
    instance = Manager.__new__(Manager)
    instance._config_helper = MagicMock()
    composite = CompositeMessageBus()
    composite.add_bus(bus)
    instance._message_bus = composite
    return instance


async def test_the_saved_credentials_reach_the_client(manager, bus):
    manager._config_helper.get_config.return_value = {
        "mqtt": {
            "host": "localhost",
            "port": 1883,
            "username": "boneio",
            "password": "nowe-haslo",
        }
    }

    await manager._reload_mqtt_credentials()

    bus.reload_credentials.assert_awaited_once_with(
        host="localhost", port=1883, username="boneio", password="nowe-haslo"
    )


async def test_credentials_the_file_does_not_carry_are_kept(manager, bus):
    """They can come from the command line, and a reload must not throw
    those away just because config.yaml is silent about them."""
    manager._config_helper.get_config.return_value = {"mqtt": {"host": "localhost"}}

    await manager._reload_mqtt_credentials()

    bus.reload_credentials.assert_awaited_once_with(
        host="localhost", port=1883, username="boneio", password="boneio123"
    )


async def test_a_bus_that_is_not_mqtt_is_passed_over(manager):
    """Lox UDP and the local loopback bus have no broker to reconnect to."""
    other = MagicMock(spec=[])
    manager._message_bus.add_bus(other)
    manager._config_helper.get_config.return_value = {
        "mqtt": {"host": "localhost", "password": "nowe-haslo"}
    }

    await manager._reload_mqtt_credentials()  # must not raise


async def test_no_mqtt_section_is_not_an_error(manager, bus):
    manager._config_helper.get_config.return_value = {}

    await manager._reload_mqtt_credentials()

    bus.reload_credentials.assert_not_awaited()


async def test_the_section_is_reachable_by_a_targeted_reload():
    """The panel asks for one section by name; `mqtt` has to be a name it
    knows, or the save goes back to waiting for a restart."""
    import inspect

    source = inspect.getsource(Manager.reload_config)
    assert "_reload_mqtt_credentials" in source
