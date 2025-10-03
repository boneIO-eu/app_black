"""
Special unique implementation of asyncio.Queue for boneIO.
If MQTT is down then regular queue can append multiple ON/OFF for same topic.
After re-connection it would send all messages. It's not necessary, last payload of same topic is enough.
"""
import asyncio
from typing import Any


class UniqueQueue(asyncio.Queue):
    """Unique implementation of asyncio.Queue that handles MQTT connection state."""

    def __init__(self, maxsize: int = 0):
        """Initialize the queue."""
        super().__init__(maxsize=maxsize)
        self._unique_items: dict[str, tuple[Any, ...]] = {}
        self._is_connected = False

    def set_connected(self, state: bool) -> None:
        """Set the connection state."""
        self._is_connected = state

    def _init(self, maxsize: int) -> None:
        """Initialize the internal queue storage."""
        super()._init(maxsize=maxsize)
        self._unique_items = {}

    def _put(self, item: tuple[str, Any, bool]) -> None:
        """Put an item into the queue.
        
        If MQTT is not connected:
            - If topic exists, replace the old message
            - If topic doesn't exist, add new message
        If MQTT is connected:
            - Add all messages to queue
        
        Args:
            item: Tuple of (topic, payload, retain)
        """
        topic = item[0]
        
        if not self._is_connected:
            # When disconnected, replace existing messages for same topic
            if topic in self._unique_items:
                self._queue.remove(self._unique_items[topic])
            super()._put(item)
            self._unique_items[topic] = item
        else:
            # When connected, queue all messages
            super()._put(item)
            self._unique_items[topic] = item

    def _get(self) -> tuple[str, Any, bool]:
        """Get an item from the queue and remove it from unique items tracking."""
        item = super()._get()
        if item[0] in self._unique_items:
            del self._unique_items[item[0]]
        return item
