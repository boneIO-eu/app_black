"""State files manager."""
from __future__ import annotations
import asyncio
import logging
import json
from typing import Any
from concurrent.futures import ThreadPoolExecutor

_LOGGER = logging.getLogger(__name__)


class StateManager:
    """StateManager to load and save states to file."""

    def __init__(self, state_file: str) -> None:
        """Initialize disk StateManager."""
        self._loop = asyncio.get_event_loop()
        self._lock = asyncio.Lock()
        self._file = state_file
        self._state = self.load_states()
        _LOGGER.info("Loaded state file from %s", self._file)
        self._file_uptodate = False
        self._save_attributes_callback = None
        self.executor = ThreadPoolExecutor()

    def load_states(self) -> dict:
        """Load state file."""
        try:
            with open(self._file, "r") as state_file:
                datastore = json.load(state_file)
                return datastore
        except FileNotFoundError:
            pass
        return {}

    def del_attribute(self, attr_type: str, attribute: str) -> None:
        """Delete attribute"""
        if attr_type in self._state and attribute in self._state[attr_type]:
            del self._state[attr_type][attribute]

    def save_attribute(self, attr_type: str, attribute: str, value: str) -> None:
        """Save single attribute to file."""
        if attr_type not in self._state:
            self._state[attr_type] = {}
        self._state[attr_type][attribute] = value
        if self._save_attributes_callback is not None:
            print(self._save_attributes_callback)
            self._save_attributes_callback.cancel()
            self._save_attributes_callback = None
        self._save_attributes_callback = self._loop.call_later(1, lambda: self._loop.create_task(self.save_state()))

    def get(self, attr_type: str, attr: str, default_value: Any = None) -> Any:
        """Retrieve attribute from json."""
        attrs = self._state.get(attr_type)
        if attrs:
            return attrs.get(attr, default_value)
        return default_value

    @property
    def state(self) -> dict:
        """Retrieve all states."""
        return self._state
    
    def _save_state(self) -> None:
        with open(self._file, "w+", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)

    async def save_state(self) -> None:
        """Async save state."""
        if self._lock.locked():
            # Let's not save state if something happens same time.
            return
        async with self._lock:
            self._loop.run_in_executor(None, self._save_state)
