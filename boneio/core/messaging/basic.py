"""Message bus abstraction for BoneIO."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from collections.abc import Awaitable, Callable

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

class MessageBus(ABC):
    """Base class for message handling."""
    
    @abstractmethod
    def send_message(
        self,
        topic: str,
        payload: str | int | dict[str, str | float | int | None] | None,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        """Send a message.
        
        Args:
            topic: MQTT topic
            payload: Message payload
            retain: Whether to retain the message
            qos: Quality of Service level (0, 1, or 2)
        """
        pass

    @property
    @abstractmethod
    def state(self) -> bool:
        """Get bus state."""
        pass
        
    @abstractmethod
    async def start_client(self) -> None:
        """Start the message bus client."""
        pass

    @abstractmethod
    def set_manager(self, manager: Manager) -> None:
        """Set manager."""
        pass

    @abstractmethod
    async def announce_offline(self) -> None:
        """Announce that the device is offline."""
        pass

    @abstractmethod
    async def subscribe_and_listen(self, topic: str, callback: Callable[[str, str], Awaitable[None]]) -> None:
        """Subscribe to a topic and listen for messages."""
        pass

    @abstractmethod
    async def unsubscribe_and_stop_listen(self, topic: str) -> None:
        """Unsubscribe from a topic and stop listening."""
        pass

