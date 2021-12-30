"""
Special unique implementation of asyncio.Queue for boneIO.
If MQTT is down then regular queue can append multiple ON/OFF for same topic.
After re-connection it would send all messages. It's not necessary, last payload of same topic is enough.
"""
import asyncio


class UniqueQueue(asyncio.Queue):
    """Unique implementation of asyncio.Queue."""

    def _init(self, maxsize):
        """Create unique dict of tuple[0]."""
        super()._init(maxsize=maxsize)
        self._unique_set = {}

    def _put(self, item):
        """If item does not exists add it.
        If exists remove old one and put new one in the beginning of the queue."""
        if item[0] not in self._unique_set:
            super()._put(item)
            self._unique_set[item[0]] = item
        else:
            self._queue.remove(self._unique_set[item[0]])
            super()._put(item)
            self._unique_set[item[0]] = item

    def _get(self):
        """Get item and remove it."""
        item = super()._get()
        del self._unique_set[item[0]]
        return item
