"""Tests for CompositeMessageBus."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.core.messaging.basic import MessageBus
from boneio.core.messaging.composite import CompositeMessageBus


class MockMessageBus(MessageBus):
    def __init__(self):
        self.send_message_mock = MagicMock()
        self.state_value = False
        self.start_client_mock = AsyncMock()
        self.set_manager_mock = MagicMock()
        self.announce_offline_mock = AsyncMock()
        self.subscribe_mock = AsyncMock()
        self.unsubscribe_mock = AsyncMock()

    def send_message(self, topic, payload, retain=False, qos=0):
        self.send_message_mock(topic, payload, retain, qos)

    @property
    def state(self) -> bool:
        return self.state_value

    async def start_client(self):
        await self.start_client_mock()

    def set_manager(self, manager):
        self.set_manager_mock(manager)

    async def announce_offline(self):
        await self.announce_offline_mock()

    async def subscribe_and_listen(self, topic, callback):
        await self.subscribe_mock(topic, callback)

    async def unsubscribe_and_stop_listen(self, topic):
        await self.unsubscribe_mock(topic)


@pytest.mark.asyncio
async def test_composite_bus_send_message():
    """Test send_message broadcasts to all buses."""
    bus1 = MockMessageBus()
    bus2 = MockMessageBus()

    composite = CompositeMessageBus()
    composite.add_bus(bus1)
    composite.add_bus(bus2)

    composite.send_message("test/topic", "payload")

    bus1.send_message_mock.assert_called_once_with("test/topic", "payload", False, 0)
    bus2.send_message_mock.assert_called_once_with("test/topic", "payload", False, 0)


@pytest.mark.asyncio
async def test_composite_bus_state():
    """Test composite state is true if any bus is true."""
    bus1 = MockMessageBus()
    bus2 = MockMessageBus()

    composite = CompositeMessageBus()
    composite.add_bus(bus1)
    composite.add_bus(bus2)

    assert composite.state is False

    bus1.state_value = True
    assert composite.state is True


@pytest.mark.asyncio
async def test_composite_bus_async_methods():
    """Test async methods delegate to all buses."""
    bus1 = MockMessageBus()
    bus2 = MockMessageBus()

    composite = CompositeMessageBus()
    composite.add_bus(bus1)
    composite.add_bus(bus2)

    await composite.start_client()
    bus1.start_client_mock.assert_awaited_once()
    bus2.start_client_mock.assert_awaited_once()

    await composite.announce_offline()
    bus1.announce_offline_mock.assert_awaited_once()
    bus2.announce_offline_mock.assert_awaited_once()
