"""System sensors for BoneIO.

This module provides sensors for monitoring system resources:
- Disk usage
- Memory usage  
- CPU usage
- System uptime

These sensors are automatically created and send data to Home Assistant
via MQTT discovery.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import psutil

from boneio.core.sensor import BaseSensor
from boneio.core.utils import TimePeriod

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)


class DiskUsageSensor(BaseSensor):
    """Sensor for monitoring disk usage.
    
    Reports disk usage percentage for the root partition.
    Sends data to Home Assistant as a sensor with device_class 'data_size'.
    
    Args:
        manager: Manager instance
        message_bus: MessageBus for MQTT
        topic_prefix: MQTT topic prefix
        update_interval: How often to update (default: 60s)
        mount_point: Disk mount point to monitor (default: '/')
    """
    
    def __init__(
        self,
        manager: Manager,
        message_bus: MessageBus,
        topic_prefix: str,
        update_interval: TimePeriod | None = None,
        mount_point: str = "/",
        **kwargs,
    ) -> None:
        """Initialize disk usage sensor."""
        if update_interval is None:
            update_interval = TimePeriod(seconds=60)
        
        self._mount_point = mount_point
        
        super().__init__(
            id="disk_usage",
            name="Disk Usage",
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            update_interval=update_interval,
            unit_of_measurement="%",
            **kwargs,
        )
        
        _LOGGER.info("Initialized DiskUsageSensor for mount point %s", mount_point)

    @property
    def device_class(self) -> str:
        """Get Home Assistant device class.
        
        Returns:
            Device class string
        """
        return "data_size"

    @property
    def state_class(self) -> str:
        """Get Home Assistant state class.
        
        Returns:
            State class string
        """
        return "measurement"

    async def async_update(self, timestamp: float) -> None:
        """Fetch disk usage and publish to MQTT.
        
        Args:
            timestamp: Current timestamp
        """
        try:
            disk = psutil.disk_usage(self._mount_point)
            usage_percent = round(disk.percent, 1)
            
            _LOGGER.debug(
                "Disk usage for %s: %.1f%% (used: %d bytes, total: %d bytes)",
                self._mount_point,
                usage_percent,
                disk.used,
                disk.total
            )
            
            self._state = usage_percent
            self._publish_state(timestamp=timestamp)
            
        except Exception as err:
            _LOGGER.error("Error reading disk usage: %s", err)


class MemoryUsageSensor(BaseSensor):
    """Sensor for monitoring memory (RAM) usage.
    
    Reports memory usage percentage.
    
    Args:
        manager: Manager instance
        message_bus: MessageBus for MQTT
        topic_prefix: MQTT topic prefix
        update_interval: How often to update (default: 30s)
    """
    
    def __init__(
        self,
        manager: Manager,
        message_bus: MessageBus,
        topic_prefix: str,
        update_interval: TimePeriod | None = None,
        **kwargs,
    ) -> None:
        """Initialize memory usage sensor."""
        if update_interval is None:
            update_interval = TimePeriod(seconds=30)
        
        super().__init__(
            id="memory_usage",
            name="Memory Usage",
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            update_interval=update_interval,
            unit_of_measurement="%",
            **kwargs,
        )
        
        _LOGGER.info("Initialized MemoryUsageSensor")

    @property
    def device_class(self) -> str:
        """Get Home Assistant device class."""
        return "data_size"

    @property
    def state_class(self) -> str:
        """Get Home Assistant state class."""
        return "measurement"

    async def async_update(self, timestamp: float) -> None:
        """Fetch memory usage and publish to MQTT.
        
        Args:
            timestamp: Current timestamp
        """
        try:
            memory = psutil.virtual_memory()
            usage_percent = round(memory.percent, 1)
            
            _LOGGER.debug(
                "Memory usage: %.1f%% (used: %d bytes, total: %d bytes)",
                usage_percent,
                memory.used,
                memory.total
            )
            
            self._state = usage_percent
            self._publish_state(timestamp=timestamp)
            
        except Exception as err:
            _LOGGER.error("Error reading memory usage: %s", err)


class CpuUsageSensor(BaseSensor):
    """Sensor for monitoring CPU usage.
    
    Reports CPU usage percentage.
    
    Args:
        manager: Manager instance
        message_bus: MessageBus for MQTT
        topic_prefix: MQTT topic prefix
        update_interval: How often to update (default: 10s)
    """
    
    def __init__(
        self,
        manager: Manager,
        message_bus: MessageBus,
        topic_prefix: str,
        update_interval: TimePeriod | None = None,
        **kwargs,
    ) -> None:
        """Initialize CPU usage sensor."""
        if update_interval is None:
            update_interval = TimePeriod(seconds=10)
        
        super().__init__(
            id="cpu_usage",
            name="CPU Usage",
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            update_interval=update_interval,
            unit_of_measurement="%",
            **kwargs,
        )
        
        _LOGGER.info("Initialized CpuUsageSensor")

    @property
    def device_class(self) -> str:
        """Get Home Assistant device class."""
        return "power_factor"  # No specific device_class for CPU, use generic

    @property
    def state_class(self) -> str:
        """Get Home Assistant state class."""
        return "measurement"

    async def async_update(self, timestamp: float) -> None:
        """Fetch CPU usage and publish to MQTT.
        
        Args:
            timestamp: Current timestamp
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            usage_percent = round(cpu_percent, 1)
            
            _LOGGER.debug("CPU usage: %.1f%%", usage_percent)
            
            self._state = usage_percent
            self._publish_state(timestamp=timestamp)
            
        except Exception as err:
            _LOGGER.error("Error reading CPU usage: %s", err)
