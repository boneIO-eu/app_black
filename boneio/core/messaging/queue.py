"""
Special unique implementation of asyncio.Queue for boneIO.
If MQTT is down then regular queue can append multiple ON/OFF for same topic.
After re-connection it would send all messages. It's not necessary, last payload of same topic is enough.
"""
import asyncio
from collections import deque
from typing import Any

from boneio.models.mqtt import MQTTMessageSend


class UniqueQueue(asyncio.Queue[MQTTMessageSend]):
    """Unique implementation of asyncio.Queue that handles MQTT connection state.
    
    This queue deduplicates messages by topic when MQTT is disconnected.
    Only the last message for each topic is kept.
    """

    _queue: deque[Any]  # Declare internal queue attribute for type checker

    def __init__(self, maxsize: int = 0):
        """Initialize the queue."""
        super().__init__(maxsize=maxsize)
        self._unique_items: dict[str, MQTTMessageSend] = {}
        self._is_connected = False

    def set_connected(self, state: bool) -> None:
        """Set the connection state."""
        self._is_connected = state

    def _init(self, maxsize: int) -> None:
        """Initialize the internal queue storage."""
        super()._init(maxsize=maxsize)
        self._unique_items = {}

    def _put(self, item: MQTTMessageSend) -> None:
        """Put an item into the queue.
        
        If MQTT is not connected:
            - If topic exists, replace the old message
            - If topic doesn't exist, add new message
        If MQTT is connected:
            - Add all messages to queue
        
        Args:
            item: MQTTMessageSend with topic, payload, qos, and retain
        """
        if not self._is_connected:
            # When disconnected, replace existing messages for same topic
            if item.topic in self._unique_items:
                old_item = self._unique_items[item.topic]
                self._queue.remove(old_item)
            super()._put(item)
            self._unique_items[item.topic] = item
        else:
            # When connected, queue all messages
            super()._put(item)
            self._unique_items[item.topic] = item

    def _get(self) -> MQTTMessageSend:
        """Get an item from the queue and remove it from unique items tracking."""
        item = super()._get()
        if item.topic in self._unique_items:
            del self._unique_items[item.topic]
        return item
