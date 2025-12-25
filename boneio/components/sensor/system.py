"""System information sensors.

This module provides sensors that report system information like
serial number, hostname, etc.
"""

from __future__ import annotations

import logging

from boneio.core.sensor import BaseSensor
from boneio.core.system import get_serial_from_mac
from boneio.core.utils import TimePeriod

_LOGGER = logging.getLogger(__name__)


class SerialNumberSensor(BaseSensor):
    """Serial number sensor based on MAC address.
    
    This sensor generates a unique serial number for the BoneIO device
    based on the last 6 characters of the MAC address. The serial number
    is prefixed with "blk" (BoneIO Black).
    
    The sensor updates every 60 minutes by default and uses BaseSensor
    for MQTT integration, async updates, and state management.
    
    Args:
        id: Sensor identifier (default: "serial_number")
        name: Human-readable name (default: "Serial Number")
        **kwargs: Additional arguments (manager, message_bus, topic_prefix, etc.)
        
    Example:
        >>> sensor = SerialNumberSensor(
        ...     name="Serial Number",
        ...     id="serial_number",
        ...     manager=manager,
        ...     message_bus=message_bus,
        ...     topic_prefix="boneio"
        ... )
        >>> # Serial number will be like: "blk8c7df0"
    """

    def __init__(
        self,
        id: str = "serial_number",
        name: str = "Serial Number",
        **kwargs
    ) -> None:
        """Initialize serial number sensor.
        
        Args:
            id: Sensor identifier
            name: Human-readable name
            **kwargs: Additional arguments passed to BaseSensor
        """
        # Update every 60 minutes (MAC address rarely changes)
        kwargs.setdefault('update_interval', TimePeriod(minutes=60))
        
        super().__init__(
            id=id,
            name=name,
            **kwargs
        )
        
        _LOGGER.info("Configured serial number sensor '%s'", self.id)

    async def async_update(self, timestamp: float) -> None:
        """Update serial number from MAC address.
        
        This method reads the MAC address from the network interface
        and generates a serial number from the last 6 characters.
        
        Args:
            timestamp: Current timestamp
        """
        try:
            serial = get_serial_from_mac()
            
            if not serial:
                _LOGGER.warning("Could not retrieve serial number from MAC address")
                return
            
            self._state = serial
            
            _LOGGER.debug("Serial number updated: %s", self._state)
            
            # Publish to MQTT and EventBus
            self._publish_state(timestamp=timestamp)
            
        except Exception as err:
            _LOGGER.error("Error updating serial number sensor: %s", err)
