"""State files manager."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

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

    def load_states(self) -> dict:
        """Load state file.

        If the file is corrupted or contains invalid JSON, logs an error,
        resets the file to an empty state, and returns an empty dictionary.
        All devices will use their default state (typically OFF).

        Returns:
            dict: The loaded state or empty dict if file is missing/corrupted.
        """
        try:
            with open(self._file) as state_file:
                datastore = json.load(state_file)
                return datastore
        except FileNotFoundError:
            _LOGGER.debug("State file %s not found, starting with empty state", self._file)
        except json.JSONDecodeError as err:
            _LOGGER.error(
                "State file %s is corrupted (JSON error: %s). "
                "Resetting to empty state. All devices will use default state (OFF).",
                self._file,
                err,
            )
            self._reset_state_file()
        except (OSError, IOError) as err:
            _LOGGER.error(
                "Failed to read state file %s: %s. Starting with empty state.",
                self._file,
                err,
            )
        return {}

    def _reset_state_file(self) -> None:
        """Reset state file to empty valid JSON.

        Creates a backup of the corrupted file before resetting.
        """
        import shutil
        from datetime import datetime

        try:
            # Create backup of corrupted file
            backup_file = f"{self._file}.corrupted.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(self._file, backup_file)
            _LOGGER.info("Corrupted state file backed up to %s", backup_file)

            # Reset to empty state
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)
            _LOGGER.info("State file %s reset to empty state", self._file)
        except (OSError, IOError) as err:
            _LOGGER.warning(
                "Failed to reset state file %s: %s. Continuing with empty state in memory.",
                self._file,
                err,
            )

    def del_attribute(self, attr_type: str, attribute: str) -> None:
        """Delete attribute"""
        if attr_type in self._state and attribute in self._state[attr_type]:
            del self._state[attr_type][attribute]

    def save_attribute(
        self, attr_type: str, attribute: str, value: str
    ) -> None:
        """Save single attribute to file."""
        if attr_type not in self._state:
            self._state[attr_type] = {}
        self._state[attr_type][attribute] = value
        if self._save_attributes_callback is not None:
            self._save_attributes_callback.cancel()
            self._save_attributes_callback = None
        self._save_attributes_callback = self._loop.call_later(
            1, lambda: self._loop.create_task(self.save_state())
        )

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
            await self._loop.run_in_executor(None, self._save_state)
