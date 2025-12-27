"""Host data aggregation for display purposes.

This module provides classes to aggregate and format system data
for OLED display and other UI components.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from boneio.const import (
    CPU,
    DISK,
    HOST,
    INA219,
    IP,
    MEMORY,
    NETWORK,
    SWAP,
    UPTIME,
)
from boneio.core.system.monitor import (
    get_cpu_info,
    get_disk_info,
    get_memory_info,
    get_network_info,
    get_swap_info,
    get_uptime,
)
from boneio.core.utils import AsyncUpdater, TimePeriod
from boneio.models import HostSensorState
from boneio.models.events import HostEvent
from boneio.version import __version__

if TYPE_CHECKING:
    from boneio.core.events import EventBus
    from boneio.core.manager import Manager
    from boneio.hardware.gpio.input import GpioBaseClass
    from boneio.hardware.i2c import INA219 as INA219Class
    from boneio.hardware.i2c import MCP9808, PCT2075

_LOGGER = logging.getLogger(__name__)


class HostSensor(AsyncUpdater):
    """Host sensor for periodic system monitoring.
    
    This class wraps system monitoring functions and periodically
    updates their values, sending events to the EventBus.
    
    Args:
        event_bus: EventBus instance for triggering events
        update_function: Function to call for getting current values
        static_data: Static data to merge with dynamic data
        id: Unique sensor identifier
        type: Sensor type name
        **kwargs: Additional arguments passed to AsyncUpdater
    """

    def __init__(
        self,
        event_bus: EventBus,
        update_function: Callable,
        static_data: dict | None,
        id: str,
        type: str,
        **kwargs,
    ) -> None:
        """Initialize host sensor."""
        self._update_function = update_function
        self._static_data = static_data
        self._state = {}
        self._type = type
        self._event_bus = event_bus
        self._loop = asyncio.get_event_loop()
        self.id = id
        super().__init__(**kwargs)
        self._loop.create_task(self.async_update(time.time()))

    async def async_update(self, timestamp: float) -> None:
        """Update sensor state and trigger event.
        
        Args:
            timestamp: Current timestamp
        """
        self._state = self._update_function()
        sensor_state = HostSensorState(
            id=self.id,
            name=self._type,
            state="new_state",  # Doesn't matter here, as we fetch everything in OLED
            timestamp=timestamp,
        )
        self._event_bus.trigger_event(HostEvent(
            entity_id=self.id, 
            state=sensor_state
        ))

    @property
    def state(self) -> dict:
        """Get current sensor state.
        
        Returns:
            Dictionary with sensor data (merged with static data if present)
        """
        if self._static_data:
            return {**self._static_data, **self._state}
        return self._state


class HostData:
    """Host data aggregator for OLED display and Web UI.
    
    This class aggregates system statistics, sensor data, and device states
    for display purposes. It creates HostSensor instances for each enabled
    monitoring type and provides methods to retrieve formatted data.
    
    Args:
        output: Dictionary of output devices grouped by expander
        inputs: Dictionary of input devices
        temp_sensor: Optional temperature sensor
        ina219: Optional INA219 power sensor
        manager: Manager instance for accessing system state
        event_bus: EventBus for triggering events
        enabled_screens: List of enabled screen types
        extra_sensors: List of extra sensor configurations
    """

    def __init__(
        self,
        output: dict,
        inputs: dict[str, GpioBaseClass],
        temp_sensor: PCT2075 | MCP9808 | None,
        ina219: INA219Class | None,
        manager: Manager,
        event_bus: EventBus,
        enabled_screens: list[str],
        extra_sensors: list[dict],
    ) -> None:
        """Initialize HostData."""
        self._manager = manager
        self._hostname = socket.gethostname()
        self._temp_sensor = temp_sensor
        
        # Define host statistics monitoring
        host_stats = {
            NETWORK: {
                "f": get_network_info,
                "update_interval": TimePeriod(seconds=60),
            },
            CPU: {
                "f": get_cpu_info,
                "update_interval": TimePeriod(seconds=5),
            },
            DISK: {
                "f": get_disk_info,
                "update_interval": TimePeriod(seconds=60),
            },
            MEMORY: {
                "f": get_memory_info,
                "update_interval": TimePeriod(seconds=10),
            },
            SWAP: {
                "f": get_swap_info,
                "update_interval": TimePeriod(seconds=60),
            },
            UPTIME: {
                "f": lambda: (
                    {
                        "uptime": {
                            "data": get_uptime(),
                            "fontSize": "small",
                            "row": 2,
                            "col": 3,
                        },
                        "MQTT": {
                            "data": "CONN" if manager.mqtt_state else "DOWN",
                            "fontSize": "small",
                            "row": 3,
                            "col": 60,
                        },
                        "T": {
                            "data": f"{getattr(self._temp_sensor, 'state', 'N/A')} C",
                            "fontSize": "small",
                            "row": 3,
                            "col": 3,
                        },
                    }
                    if self._temp_sensor
                    else {
                        "uptime": {
                            "data": get_uptime(),
                            "fontSize": "small",
                            "row": 2,
                            "col": 3,
                        }
                    }
                ),
                "static": {
                    HOST: {
                        "data": self._hostname,
                        "fontSize": "small",
                        "row": 0,
                        "col": 3,
                    },
                    "ver": {
                        "data": __version__,
                        "fontSize": "small",
                        "row": 1,
                        "col": 3,
                    },
                },
                "update_interval": TimePeriod(seconds=30),
            },
        }
        
        # Add INA219 power monitoring if available
        if ina219 is not None:

            def get_ina_values():
                return {
                    sensor.device_class: f"{sensor.state} {sensor.unit_of_measurement}"
                    for sensor in ina219.sensors.values()
                }

            host_stats[INA219] = {
                "f": get_ina_values,
                "update_interval": TimePeriod(seconds=60),
            }
        
        # Add extra sensors (modbus, dallas, etc.)
        if extra_sensors:

            def get_extra_sensors_values():
                output = {}
                for sensor in extra_sensors[:3]:
                    sensor_type = sensor.get("sensor_type")
                    sensor_id = sensor.get("sensor_id")
                    if sensor_type == "modbus":
                        modbus_id = sensor.get("modbus_id")
                        if not modbus_id:
                            continue
                        _modbus_coordinator = manager.modbus.get_all_coordinators().get(modbus_id)
                        if _modbus_coordinator:
                            if not sensor_id:
                                continue
                            entity = _modbus_coordinator.get_entity_by_name(
                                sensor_id
                            )
                            if not entity:
                                _LOGGER.warning(
                                    "Sensor %s not found", sensor_id
                                )
                                continue
                            short_name = "".join(
                                [x[:3] for x in entity.name.split()]
                            )
                            if entity.state is not None:
                                output[short_name] = (
                                    f"{round(float(entity.state), 2)} {entity.unit_of_measurement}"
                                )
                            else:
                                output[short_name] = f"N/A {entity.unit_of_measurement}"
                    elif sensor_type == "dallas":
                        for single_sensor in manager.sensors.get_dallas_sensors():
                            if sensor_id == single_sensor.id.lower():
                                output[single_sensor.name] = (
                                    f"{round(single_sensor.state, 2)} C"
                                )
                return output

            host_stats["extra_sensors"] = {
                "f": get_extra_sensors_values,
                "update_interval": TimePeriod(seconds=60),
            }
        
        # Create HostSensor instances for enabled screens
        self._data = {}
        for k, _v in host_stats.items():
            if k not in enabled_screens:
                continue
            self._data[k] = HostSensor(
                update_function=_v["f"],
                static_data=_v.get("static"),
                event_bus=event_bus,
                manager=manager,
                id=f"{k}_hoststats",
                type=k,
                update_interval=_v["update_interval"],
            )
        
        self._output = output
        _LOGGER.debug("HostData initialized with outputs: %s", list(output.keys()) if output else "None")
        
        # Group inputs for display (25 inputs per screen)
        self._inputs = {
            f"Inputs screen {i + 1}": list(inputs.values())[
                i * 25 : (i + 1) * 25
            ]
            for i in range((len(inputs) + 24) // 25)
        }
        
        self._loop = asyncio.get_running_loop()

    @property
    def web_url(self) -> str | None:
        """Get web UI URL if web server is enabled.
        
        Returns:
            URL string like "http://192.168.1.100:8090" or None
        """
        if not self._manager.is_web_on:
            return None
        network_state = self._data[NETWORK].state
        if IP in network_state:
            return f"{self._manager.config_helper.http_proto}://{network_state[IP]}:{self._manager.config_helper.ha_configuration_port}"
        return None

    def get(self, type: str) -> dict | str | None:
        """Get data for specified type.
        
        Args:
            type: Data type to retrieve (output name, input screen, 'web', or stat type)
            
        Returns:
            Dictionary with data, URL string, or None if not found
        """
        # _LOGGER.debug("HostData.get called with type='%s', outputs=%s", type, list(self._output.keys()) if self._output else "None")
        
        if type in self._output:
            return self._get_output(type)
        if type in self._inputs:
            return self._get_input(type)
        if type == "web":
            return self.web_url
        if type in self._data:
            return self._data[type].state
        
        _LOGGER.debug("HostData.get returning None for type='%s'", type)
        return None

    def _get_output(self, type: str) -> dict:
        """Get formatted output device states.
        
        Args:
            type: Output group name
            
        Returns:
            Dictionary mapping output IDs to their names and states
        """
        out = {}
        for output in self._output[type].values():
            out[output.id] = {
                "name": output.name,
                "state": output.state
            }
        return out

    def _get_input(self, type: str) -> dict:
        """Get formatted input device states.
        
        Args:
            type: Input screen name
            
        Returns:
            Dictionary mapping input IDs to their names and states
        """
        inputs = {}
        for input in self._inputs[type]:
            inputs[input.id] = {
                "name": input.name,
                "state": input.last_state[0].upper() if input.last_state and input.last_state != "Unknown" else ""
            }
        return inputs

    @property
    def inputs_length(self) -> int:
        """Get number of input screens.
        
        Returns:
            Number of input screens (each screen shows up to 25 inputs)
        """
        return len(self._inputs)
