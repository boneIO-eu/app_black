"""Tests for LoxUDPClient."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.core.messaging.lox import LoxUDPClient, LoxUDPProtocol


@pytest.fixture
def config_helper_mock():
    mock = MagicMock()
    mock.cmd_topic_prefix = "boneio/test/cmd/"
    return mock


@pytest.fixture
def manager_mock():
    mock = AsyncMock()
    mock.receive_message = AsyncMock()
    mock.outputs = MagicMock()
    mock.outputs.get_output = MagicMock(return_value=True)  # By default treat device as output
    mock.outputs.get_output_group = MagicMock(return_value=None)
    mock.covers = MagicMock()
    return mock


def test_lox_send_message(config_helper_mock):
    """Test send_message formats UDP payload correctly."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    # Valid output topic
    client.send_message("boneio/output/relay1/state", "ON")
    client._transport.sendto.assert_called_once_with(b"relay1=ON", ("127.0.0.1", 4444))

    client._transport.reset_mock()

    # Ignore command topics
    client.send_message("boneio/output/relay1/set", "ON")
    client._transport.sendto.assert_not_called()

    # Ignore discovery payloads (dicts)
    client.send_message("homeassistant/switch/test/config", {"name": "test"})
    client._transport.sendto.assert_not_called()


@pytest.mark.asyncio
async def test_lox_handle_incoming(config_helper_mock, manager_mock):
    """Test incoming UDP payload is parsed and routed to Manager."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client.set_manager(manager_mock)

    # Output message
    await client._handle_incoming("relay1", "ON")
    manager_mock.receive_message.assert_awaited_once_with("boneio/test/cmd/output/relay1/set", "ON")

    manager_mock.receive_message.reset_mock()

    # Cover message
    manager_mock.outputs.get_output.return_value = None
    manager_mock.outputs.get_output_group.return_value = None
    manager_mock.covers.get_cover.return_value = True

    await client._handle_incoming("cover1", "UP")
    manager_mock.receive_message.assert_awaited_once_with("boneio/test/cmd/cover/cover1/set", "UP")


@pytest.mark.asyncio
async def test_lox_protocol():
    """Test LoxUDPProtocol parsing."""
    callback = AsyncMock()
    protocol = LoxUDPProtocol(callback)

    # With value
    protocol.datagram_received(b"relay1=ON", ("127.0.0.1", 1234))
    # Provide a slight delay for event loop to process create_task
    await asyncio.sleep(0)
    callback.assert_awaited_with("relay1", "ON")

    callback.reset_mock()

    # Without value (simple press)
    protocol.datagram_received(b"button1", ("127.0.0.1", 1234))
    await asyncio.sleep(0)
    callback.assert_awaited_with("button1", "pressed")
