"""Composite Message Bus for handling multiple protocols simultaneously."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from boneio.core.messaging.basic import MessageBus

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.integration.homeassistant import HomeAssistantDiscoveryMessage

_LOGGER = logging.getLogger(__name__)


class CompositeMessageBus(MessageBus):
    """Message bus that delegates to multiple underlying message buses."""

    def __init__(self) -> None:
        """Initialize composite bus with an empty list of message buses."""
        self._buses: list[MessageBus] = []

    def add_bus(self, bus: MessageBus) -> None:
        """Add a new bus to the composite."""
        self._buses.append(bus)

    def send_message(
        self,
        topic: str,
        payload: str | int | bytes | dict[str, Any] | HomeAssistantDiscoveryMessage | None,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        """Send a message to all buses."""
        for bus in self._buses:
            try:
                bus.send_message(topic, payload, retain, qos)
            except Exception as e:
                _LOGGER.error("Error sending message on bus %s: %s", type(bus).__name__, e)

    @property
    def state(self) -> bool:
        """Get bus state. Returns True if at least one bus is connected."""
        if not self._buses:
            return False
        return any(bus.state for bus in self._buses)

    async def start_client(self) -> None:
        """Start all message bus clients."""
        if not self._buses:
            return

        tasks = []
        for bus in self._buses:
            tasks.append(asyncio.create_task(bus.start_client()))

        if tasks:
            await asyncio.gather(*tasks)

    def set_manager(self, manager: "Manager") -> None:
        """Set manager on all buses."""
        for bus in self._buses:
            bus.set_manager(manager)

    async def announce_offline(self) -> None:
        """Announce offline on all buses."""
        tasks = []
        for bus in self._buses:
            tasks.append(asyncio.create_task(bus.announce_offline()))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def subscribe_and_listen(self, topic: str, callback: Callable[[str, str], Awaitable[None]]) -> None:
        """Subscribe to a topic and listen for messages on all buses."""
        for bus in self._buses:
            await bus.subscribe_and_listen(topic, callback)

    async def unsubscribe_and_stop_listen(self, topic: str) -> None:
        """Unsubscribe from a topic and stop listening on all buses."""
        for bus in self._buses:
            await bus.unsubscribe_and_stop_listen(topic)
