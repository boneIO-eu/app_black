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


def test_lox_send_message_dict_payload(config_helper_mock):
    """Test send_message correctly handles dict payloads (most common case)."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    # Dict payload with "state" key — standard output state format
    client.send_message("boneio/blk123/output/relay1", {"state": "ON"})
    client._transport.sendto.assert_called_once_with(b"relay1=ON", ("127.0.0.1", 4444))


def test_lox_send_message_string_payload(config_helper_mock):
    """Test send_message with string payload."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/output/relay1", "ON")
    client._transport.sendto.assert_called_once_with(b"relay1=ON", ("127.0.0.1", 4444))


def test_lox_send_message_cover_with_suffix(config_helper_mock):
    """Test send_message with cover state topic (has /state suffix)."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    # Cover state topics include /state suffix
    client.send_message("boneio/blk123/cover/cover1/state", "open")
    client._transport.sendto.assert_called_once_with(b"cover1=open", ("127.0.0.1", 4444))


def test_lox_send_message_cover_position(config_helper_mock):
    """Test send_message with cover position topic (has /pos suffix)."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/cover/cover1/pos", '{"position": 50}')
    client._transport.sendto.assert_called_once_with(
        b'cover1={"position": 50}', ("127.0.0.1", 4444)
    )


def test_lox_send_message_event_entity(config_helper_mock):
    """Test send_message with event entity type — should be sent to Loxone."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/event/button1", "pressed")
    client._transport.sendto.assert_called_once_with(b"button1=pressed", ("127.0.0.1", 4444))


def test_lox_send_message_binary_sensor(config_helper_mock):
    """Test send_message with binary_sensor entity type — should be sent."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/binary_sensor/door1", "pressed")
    client._transport.sendto.assert_called_once_with(b"door1=pressed", ("127.0.0.1", 4444))


def test_lox_send_message_input_entity(config_helper_mock):
    """Test send_message with input entity type — should be sent."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/input/switch1", "pressed")
    client._transport.sendto.assert_called_once_with(b"switch1=pressed", ("127.0.0.1", 4444))


def test_lox_send_message_skips_cmd_topics(config_helper_mock):
    """Test that command topics are not sent to Loxone."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/cmd/output/relay1/set", "ON")
    client._transport.sendto.assert_not_called()


def test_lox_send_message_skips_discovery(config_helper_mock):
    """Test that HA Discovery messages are not sent to Loxone."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("homeassistant/switch/test/config", {"name": "test"})
    client._transport.sendto.assert_not_called()


def test_lox_send_message_skips_none_payload(config_helper_mock):
    """Test that None payloads are ignored."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/output/relay1", None)
    client._transport.sendto.assert_not_called()


def test_lox_send_message_skips_unsupported_entity_types(config_helper_mock):
    """Test that unsupported entity types (e.g. update) are ignored."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/update/firmware", {"state": "ready"})
    client._transport.sendto.assert_not_called()


def test_lox_send_message_skips_short_topics(config_helper_mock):
    """Test that topics with fewer than 4 parts are ignored."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/state", "online")
    client._transport.sendto.assert_not_called()


def test_lox_send_message_skips_config_suffix(config_helper_mock):
    """Test that topics ending with /config are skipped."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/output/relay1/config", {"name": "test"})
    client._transport.sendto.assert_not_called()


def test_lox_send_message_dict_with_value_key(config_helper_mock):
    """Test send_message extracts 'value' key from dict payload."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client._transport = MagicMock()

    client.send_message("boneio/blk123/sensor/temp1", {"value": "22.5"})
    client._transport.sendto.assert_called_once_with(b"temp1=22.5", ("127.0.0.1", 4444))


@pytest.mark.asyncio
async def test_lox_handle_incoming(config_helper_mock, manager_mock):
    """Test incoming UDP payload is parsed and executed directly on output."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client.set_manager(manager_mock)

    # Create a proper mock output with output_type and async methods
    mock_output = AsyncMock()
    mock_output.output_type = "switch"
    mock_output.async_turn_on = AsyncMock()
    mock_output.async_turn_off = AsyncMock()
    mock_output.async_toggle = AsyncMock()

    manager_mock.outputs.get_output.return_value = mock_output
    manager_mock.outputs.get_all_outputs.return_value = {}

    # Output ON command
    await client._handle_incoming("relay1", "ON")
    mock_output.async_turn_on.assert_awaited_once()

    mock_output.async_turn_on.reset_mock()

    # Output OFF command
    await client._handle_incoming("relay1", "OFF")
    mock_output.async_turn_off.assert_awaited_once()

    # Output TOGGLE command
    await client._handle_incoming("relay1", "TOGGLE")
    mock_output.async_toggle.assert_awaited_once()

    # Cover message
    manager_mock.outputs.get_output.return_value = None
    manager_mock.outputs.get_output_group.return_value = None

    mock_cover = AsyncMock()
    mock_cover.open = AsyncMock()
    manager_mock.covers.get_cover.return_value = mock_cover

    await client._handle_incoming("cover1", "OPEN")
    mock_cover.open.assert_awaited_once()


@pytest.mark.asyncio
async def test_lox_handle_incoming_case_insensitive(config_helper_mock, manager_mock):
    """Test case-insensitive fallback for device lookup."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client.set_manager(manager_mock)

    mock_output = AsyncMock()
    mock_output.output_type = "switch"
    mock_output.async_turn_on = AsyncMock()

    # Exact match fails
    manager_mock.outputs.get_output.return_value = None
    manager_mock.outputs.get_output_group.return_value = None
    manager_mock.covers.get_cover.return_value = None
    # Case-insensitive match succeeds
    manager_mock.outputs.get_all_outputs.return_value = {"OUT_10": mock_output}

    await client._handle_incoming("out_10", "ON")
    mock_output.async_turn_on.assert_awaited_once()


@pytest.mark.asyncio
async def test_lox_handle_incoming_output_group(config_helper_mock, manager_mock):
    """Test output group commands are properly routed."""
    client = LoxUDPClient(config_helper_mock, "127.0.0.1", 4444, 4445)
    client.set_manager(manager_mock)

    mock_group = AsyncMock()
    mock_group.output_type = "switch"
    mock_group.async_turn_on = AsyncMock()

    manager_mock.outputs.get_output.return_value = None
    manager_mock.outputs.get_output_group.return_value = mock_group
    manager_mock.outputs.get_all_outputs.return_value = {}

    await client._handle_incoming("group1", "ON")
    mock_group.async_turn_on.assert_awaited_once()


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
