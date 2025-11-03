"""Async updater base class for periodic updates."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.core.manager import Manager

from boneio.core.utils.timeperiod import TimePeriod

_LOGGER = logging.getLogger(__name__)


class AsyncUpdater(ABC):
    """Base class for components that need periodic async updates.
    
    Classes inheriting from AsyncUpdater MUST implement ONE of:
    - async_update(timestamp: float) -> float | None  (for async operations)
    - update(timestamp: float) -> float | None        (for sync operations)
    
    The update method should return an optional update interval in seconds,
    or None to use the default interval.
    
    Note: This class uses ABC but doesn't use @abstractmethod to allow flexibility.
    Instead, it validates implementation at initialization time.
    """

    def __init__(self, manager: Manager, update_interval: TimePeriod, **kwargs):
        """Initialize async updater.
        
        Args:
            manager: Manager instance to register the update task
            update_interval: Time period between updates
            **kwargs: Additional arguments (passed to parent classes)
            
        Raises:
            NotImplementedError: If neither async_update nor update is implemented
            AttributeError: If subclass doesn't have 'id' attribute
        """
        # Validate that subclass has 'id' attribute
        if not hasattr(self, "id"):
            raise AttributeError(
                f"{self.__class__.__name__} must have 'id' attribute before calling AsyncUpdater.__init__"
            )
        
        # Validate that subclass implements at least one update method
        has_async_update = (
            hasattr(self, "async_update") 
            and callable(getattr(self, "async_update"))
            and self.__class__.async_update is not AsyncUpdater.async_update
        )
        has_sync_update = (
            hasattr(self, "update") 
            and callable(getattr(self, "update"))
            and self.__class__.update is not AsyncUpdater.update
        )
        
        if not (has_async_update or has_sync_update):
            raise NotImplementedError(
                f"{self.__class__.__name__} must implement either "
                "'async_update(timestamp)' or 'update(timestamp)' method"
            )
        
        self.manager = manager
        self._update_interval = update_interval or TimePeriod(seconds=60)
        self._wakeup_event = asyncio.Event()  # Event to wake up from sleep early
        self._requested_update_interval: float | None = None  # Custom interval for next update
        self.manager.append_task(coro=self._refresh, name=self.id)  # type: ignore[attr-defined]
        self._timestamp = time.time()
        
        # Log which update method will be used
        update_type = "async" if has_async_update else "sync"
        _LOGGER.debug(
            f"{self.__class__.__name__} initialized with {update_type} update method"
        )

    async def async_update(self, timestamp: float) -> float | None:
        """Perform async update operation.
        
        Override this method in subclasses that need async operations.
        Do NOT call super().async_update() in your implementation.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            Optional custom update interval in seconds, or None for default
        """
        # This is a placeholder that should be overridden
        # If not overridden, _refresh will use update() instead
        return None

    def update(self, timestamp: float) -> float | None:
        """Perform sync update operation.
        
        Override this method in subclasses that don't need async operations.
        Do NOT call super().update() in your implementation.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            Optional custom update interval in seconds, or None for default
        """
        # This is a placeholder that should be overridden
        # If not overridden, _refresh will use async_update() instead
        return None

    async def _refresh(self) -> None:
        """Internal refresh loop that calls the appropriate update method."""
        try:
            # Determine which update method to use (check once, not every loop)
            use_async = (
                self.__class__.async_update is not AsyncUpdater.async_update
            )
            
            # Perform first update immediately on startup
            
            while True:
                timestamp = time.time()
                if use_async:
                        # Use async_update (preferred)
                        update_interval = (
                            await self.async_update(timestamp=timestamp)
                            or self._update_interval.total_in_seconds
                        )
                else:
                    # Use sync update (fallback)
                    update_interval = (
                        self.update(timestamp=timestamp) 
                        or self._update_interval.total_in_seconds
                    )
                # Sleep until update_interval expires OR wakeup event is triggered
                try:
                    await asyncio.wait_for(
                        self._wakeup_event.wait(),
                        timeout=update_interval
                    )
                    # Event was triggered - wake up early
                    self._wakeup_event.clear()
                    _LOGGER.debug(f"{getattr(self, 'id', 'unknown')}: Woken up early from sleep")
                    
                    # Check if custom delay was requested before update
                    if self._requested_update_interval is not None:
                        delay = self._requested_update_interval
                        self._requested_update_interval = None
                        _LOGGER.debug(f"{getattr(self, 'id', 'unknown')}: Waiting {delay}s before update")
                        await asyncio.sleep(delay)
                except asyncio.TimeoutError:
                    # Normal timeout - continue to update
                    pass
                
        except asyncio.CancelledError:
            raise

    def request_update(self, seconds: float = 0) -> None:
        """Request update after specified seconds by waking up from sleep.
        
        This method triggers the wakeup event, causing the refresh loop
        to exit from asyncio.sleep early and perform an update after the
        specified delay.
        
        Args:
            seconds: Delay in seconds before next update. 
                    0 = immediate update (default)
                    > 0 = update after specified seconds
        """
        self._requested_update_interval = seconds
        self._wakeup_event.set()
        if seconds == 0:
            _LOGGER.debug(f"{getattr(self, 'id', 'unknown')}: Immediate update requested")
        else:
            _LOGGER.debug(f"{getattr(self, 'id', 'unknown')}: Update requested in {seconds} seconds")
    
    @property
    def last_timestamp(self) -> float:
        """Get the timestamp of the last update."""
        return self._timestamp
