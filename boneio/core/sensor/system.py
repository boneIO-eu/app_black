"""System sensors for BoneIO.

This module provides sensors for monitoring system resources:
- Disk usage (eMMC, SD card, or any mounted partition)
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


def detect_disk_sensors() -> list[dict]:
    """Detect available disk partitions and return sensor configurations.

    On BeagleBone Black:
    - eMMC is typically /dev/mmcblk1 mounted on /
    - SD card is typically /dev/mmcblk0 mounted on /media/sd or similar

    Returns:
        List of dicts with keys: id, name, mount_point, icon, device
    """
    sensors: list[dict] = []
    seen_mounts: set[str] = set()

    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception as e:
        _LOGGER.error("Failed to detect disk partitions: %s", e)
        return [{"id": "disk_usage", "name": "System Disk Usage", "mount_point": "/", "icon": "mdi:harddisk", "device": ""}]

    for part in partitions:
        mount = part.mountpoint
        device = part.device

        # Skip pseudo-filesystems and duplicates
        if mount in seen_mounts:
            continue
        if part.fstype in ("tmpfs", "devtmpfs", "squashfs", "overlay", ""):
            continue

        seen_mounts.add(mount)

        # Classify disk type by device name
        if "mmcblk0" in device:
            # SD card (first MMC device on BeagleBone)
            sensors.append({
                "id": "sd_card_usage",
                "name": "SD Card Usage",
                "mount_point": mount,
                "icon": "mdi:micro-sd",
                "device": device,
            })
        elif "mmcblk1" in device:
            # eMMC (second MMC device on BeagleBone)
            sensors.append({
                "id": "emmc_usage",
                "name": "eMMC Usage",
                "mount_point": mount,
                "icon": "mdi:harddisk",
                "device": device,
            })
        elif mount == "/":
            # Root partition on non-BeagleBone (dev machine, VM, etc.)
            sensors.append({
                "id": "disk_usage",
                "name": "System Disk Usage",
                "mount_point": mount,
                "icon": "mdi:harddisk",
                "device": device,
            })

    # Fallback: if no sensors detected, monitor root
    if not sensors:
        sensors.append({
            "id": "disk_usage",
            "name": "System Disk Usage",
            "mount_point": "/",
            "icon": "mdi:harddisk",
            "device": "",
        })

    _LOGGER.info(
        "Detected %d disk sensor(s): %s",
        len(sensors),
        [(s["id"], s["mount_point"], s["device"]) for s in sensors],
    )
    return sensors


class DiskUsageSensor(BaseSensor):
    """Sensor for monitoring disk usage on a specific mount point.
    
    Reports disk usage percentage for the given partition.
    Sends data to Home Assistant as a sensor with device_class 'data_size'.
    
    Args:
        manager: Manager instance
        message_bus: MessageBus for MQTT
        topic_prefix: MQTT topic prefix
        update_interval: How often to update (default: 60s)
        mount_point: Disk mount point to monitor (default: '/')
        sensor_id: Unique sensor identifier (default: 'disk_usage')
        name: Human-readable sensor name (default: 'System Disk Usage')
    """
    
    def __init__(
        self,
        manager: Manager,
        message_bus: MessageBus,
        topic_prefix: str,
        update_interval: TimePeriod | None = None,
        mount_point: str = "/",
        sensor_id: str = "disk_usage",
        name: str = "System Disk Usage",
        **kwargs,
    ) -> None:
        """Initialize disk usage sensor."""
        if update_interval is None:
            update_interval = TimePeriod(seconds=60)
        
        self._mount_point = mount_point
        
        super().__init__(
            id=sensor_id,
            name=name,
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            update_interval=update_interval,
            unit_of_measurement="%",
            **kwargs,
        )
        
        _LOGGER.info(
            "Initialized DiskUsageSensor '%s' for mount point %s",
            sensor_id,
            mount_point,
        )

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

        Publishes percentage as main state plus extra attributes
        (disk_total_gib, disk_used_gib, disk_free_gib) for HA.

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
            self._attributes = {
                "disk_total_gib": round(disk.total / (1024 ** 3), 2),
                "disk_used_gib": round(disk.used / (1024 ** 3), 2),
                "disk_free_gib": round(disk.free / (1024 ** 3), 2),
            }
            self._publish_state(timestamp=timestamp)

        except Exception as err:
            _LOGGER.error("Error reading disk usage for %s: %s", self._mount_point, err)


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

        Publishes percentage as main state plus extra attributes
        (memory_total_gib, memory_used_gib, memory_available_gib) for HA.

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
            self._attributes = {
                "memory_total_gib": round(memory.total / (1024 ** 3), 2),
                "memory_used_gib": round(memory.used / (1024 ** 3), 2),
                "memory_available_gib": round(memory.available / (1024 ** 3), 2),
            }
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
