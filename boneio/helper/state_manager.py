"""State files manager."""
import asyncio
import json
from typing import Any


class StateManager:
    """StateManager to load and save states to file."""

    def __init__(self, state_file: str) -> None:
        """Initialize disk StateManager."""
        self._loop = asyncio.get_event_loop()
        self._lock = asyncio.Lock()
        self._file = state_file
        self._state = self.load_states()
        self._file_uptodate = False

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
        asyncio.run_coroutine_threadsafe(self.save_state(), self._loop)

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

    async def save_state(self) -> None:
        """Async save state."""
        if self._lock.locked():
            # Let's not save state if something happens same time.
            return
        async with self._lock:
            with open(self._file, "w+", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
