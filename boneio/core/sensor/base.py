"""Base sensor class for BoneIO.

This module provides a base class that combines common sensor functionality:
- MQTT messaging (BasicMqtt)
- Periodic async updates (AsyncUpdater)
- Value filtering (Filter)
- Event bus integration
- State management
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from boneio.const import SENSOR, STATE
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import AsyncUpdater, Filter
from boneio.models import SensorState
from boneio.models.events import SensorEvent

_LOGGER = logging.getLogger(__name__)


class BaseSensor(BasicMqtt, AsyncUpdater, Filter):
    """Base class for all BoneIO sensors.
    
    This class combines BasicMqtt, AsyncUpdater, and Filter to provide
    a complete sensor implementation with MQTT integration, periodic updates,
    and value filtering capabilities.
    
    Inheriting classes should:
    1. Implement `async_update(timestamp: float)` method to fetch sensor data
    2. Call `_publish_state()` when new data is available
    3. Override properties as needed (unit_of_measurement, state, etc.)
    
    Args:
        id: Sensor identifier (unique)
        name: Human-readable sensor name
        manager: Manager instance for state management
        message_bus: MessageBus instance for MQTT communication
        topic_prefix: MQTT topic prefix
        update_interval: How often to update the sensor (TimePeriod)
        filters: List of filter expressions to apply to values
        unit_of_measurement: Unit string (e.g., '°C', 'A', 'V')
        **kwargs: Additional arguments
        
    Example:
        >>> class MySensor(BaseSensor):
        ...     async def async_update(self, timestamp: float):
        ...         value = await self._read_sensor()
        ...         if value is not None:
        ...             self._state = self._apply_filters(value=value)
        ...             self._publish_state(timestamp=timestamp)
    """

    def __init__(
        self,
        id: str,
        name: str | None = None,
        filters: list | None = None,
        unit_of_measurement: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize base sensor.
        
        Args:
            id: Sensor identifier
            name: Human-readable name (defaults to id)
            filters: List of filter configurations
            unit_of_measurement: Unit string
            **kwargs: Additional arguments for parent classes
        """
        self._loop = asyncio.get_event_loop()
        
        # Initialize BasicMqtt (ensure name is not None)
        BasicMqtt.__init__(self, id=id, name=name or id, topic_type=SENSOR, **kwargs)
        
        # Initialize Filter
        Filter.__init__(self)
        self._filters = filters or []
        
        # Sensor state
        self._state: Any = None
        self._timestamp: float | None = None
        self._unit_of_measurement = unit_of_measurement or ""
        
        # Initialize AsyncUpdater (must be last as it may start update loop)
        AsyncUpdater.__init__(self, **kwargs)
        
        _LOGGER.debug(
            "Initialized %s sensor '%s' (id: %s) with update_interval=%s",
            self.__class__.__name__,
            self.name,
            self.id,
            getattr(self, '_update_interval', 'N/A')
        )

    @property
    def state(self) -> Any:
        """Get current sensor state.
        
        Returns:
            Current state value (filtered)
        """
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        """Get unit of measurement.
        
        Returns:
            Unit string (e.g., '°C', 'A', 'V')
        """
        return self._unit_of_measurement

    @property
    def last_timestamp(self) -> float | None:
        """Get timestamp of last update.
        
        Returns:
            Unix timestamp or None if never updated
        """
        return self._timestamp

    def _publish_state(self, timestamp: float) -> None:
        """Publish current state to MQTT and EventBus.
        
        This method should be called by subclasses after updating _state.
        It handles both MQTT publishing and EventBus event triggering.
        
        Args:
            timestamp: Current timestamp for the reading
        """
        self._timestamp = timestamp
        
        # Send to MQTT
        self._message_bus.send_message(
            topic=self._send_topic,
            payload={STATE: self.state},
        )
        
        
        self.manager.event_bus.trigger_event(SensorEvent(
            entity_id=self.id,
            state=SensorState(
                id=self.id,
                name=self.name,
                state=self.state,   
                unit=self.unit_of_measurement,
                timestamp=self.last_timestamp,
            )
        ))
        
        _LOGGER.debug(
            "Published state for sensor '%s': %s %s",
            self.id,
            self.state,
            self.unit_of_measurement
        )

    async def async_update(self, timestamp: float) -> None:
        """Update sensor state.
        
        This method is called periodically by AsyncUpdater.
        Subclasses must implement this method to fetch sensor data.
        
        Args:
            timestamp: Current timestamp
            
        Raises:
            NotImplementedError: If not overridden by subclass
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement async_update()"
        )

