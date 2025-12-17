"""Virtual Energy Sensor module.

Creates virtual power/energy or water flow sensors linked to outputs.
When the linked output is ON, the sensor calculates consumption based on
configured power_usage or flow_rate.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

from boneio.const import ON
from boneio.models import SensorState
from boneio.models.events import SensorEvent

if TYPE_CHECKING:
    from boneio.core.messaging.basic import MessageBus
    from boneio.core.events.bus import EventBus
    from boneio.components.output.basic import BasicOutput

_LOGGER = logging.getLogger(__name__)


class VirtualEnergySensor:
    """Virtual energy/water sensor linked to an output.
    
    Tracks energy consumption (Wh) or water consumption (L) based on
    configured power_usage (W) or flow_rate (L/h) when the linked output is ON.
    
    Args:
        id: Unique sensor identifier
        name: Display name for Home Assistant
        output: The output to track
        message_bus: MessageBus for MQTT communication
        loop: Event loop
        topic_prefix: MQTT topic prefix
        sensor_type: 'power' or 'water'
        power_usage: Power consumption in Watts (for sensor_type='power')
        flow_rate: Flow rate in L/h (for sensor_type='water')
        area: Optional area ID for HA sub-device
    """

    def __init__(
        self,
        id: str,
        name: str,
        output: BasicOutput,
        message_bus: MessageBus,
        event_bus: "EventBus",
        loop: asyncio.AbstractEventLoop,
        topic_prefix: str,
        sensor_type: str,
        power_usage: float | None = None,
        flow_rate: float | None = None,
        area: str | None = None,
    ):
        self._id = id
        self._name = name
        self._output = output
        self._loop = loop or asyncio.get_running_loop()
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._topic_prefix = topic_prefix
        self._sensor_type = sensor_type
        self._power_usage = power_usage
        self._flow_rate = flow_rate
        self._area = area
        
        self._virtual_sensors_task = None
        
        # Counters
        self._energy_consumed_Wh = 0.0
        self._water_consumed_L = 0.0
        self._last_on_timestamp = time.time() if self._output.state == ON else None
        
        # MQTT topic for this sensor
        self._sensor_topic = f"{topic_prefix}/energy/{id}"
        
        # Subscribe to restore state from MQTT
        self._subscribe_restore_state()
        
        _LOGGER.info(
            "Initialized VirtualEnergySensor: id=%s, name=%s, output=%s, type=%s",
            id, name, output.id, sensor_type
        )

    @property
    def id(self) -> str:
        """Get sensor ID."""
        return self._id

    @property
    def name(self) -> str:
        """Get sensor name."""
        return self._name

    @property
    def output_id(self) -> str:
        """Get linked output ID."""
        return self._output.id

    @property
    def sensor_type(self) -> str:
        """Get sensor type ('power' or 'water')."""
        return self._sensor_type

    @property
    def area(self) -> str | None:
        """Get area ID."""
        return self._area

    @property
    def power_usage(self) -> float | None:
        """Get power usage in Watts."""
        return self._power_usage

    @property
    def flow_rate(self) -> float | None:
        """Get flow rate in L/h."""
        return self._flow_rate

    @property
    def last_on_timestamp(self) -> float | None:
        """Get timestamp when output was last turned ON."""
        return self._last_on_timestamp

    def start_tracking(self):
        """Start tracking consumption (called when output turns ON)."""
        self._last_on_timestamp = time.time()
        if self._virtual_sensors_task is not None and not self._virtual_sensors_task.done():
            return  # Already running
        self._virtual_sensors_task = self._loop.create_task(self._tracking_loop())
        _LOGGER.debug("Started tracking for virtual sensor %s", self._id)

    def stop_tracking(self):
        """Stop tracking consumption (called when output turns OFF)."""
        # Update one last time before stopping
        self._update_consumption()
        self._last_on_timestamp = None
        
        if self._virtual_sensors_task is not None:
            self._virtual_sensors_task.cancel()
            self._virtual_sensors_task = None
        
        # Send final state
        self._send_state()
        _LOGGER.debug("Stopped tracking for virtual sensor %s", self._id)

    async def _tracking_loop(self):
        """Periodically update and send state every 30 seconds while output is ON."""
        try:
            while self._output.state == ON:
                self._update_consumption()
                self._send_state()
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    def _update_consumption(self):
        """Update consumption counters based on elapsed time."""
        now = time.time()
        if self._output.state == ON and self._last_on_timestamp is not None:
            elapsed = now - self._last_on_timestamp
            
            if self._sensor_type == "power" and self._power_usage is not None:
                self._energy_consumed_Wh += (self._power_usage * elapsed) / 3600.0
                _LOGGER.debug(
                    "Energy updated for %s: %.4f Wh",
                    self._id, self._energy_consumed_Wh
                )
            elif self._sensor_type == "water" and self._flow_rate is not None:
                self._water_consumed_L += (self._flow_rate * elapsed) / 3600.0
                _LOGGER.debug(
                    "Water updated for %s: %.4f L",
                    self._id, self._water_consumed_L
                )
            
            self._last_on_timestamp = now

    def _subscribe_restore_state(self):
        """Subscribe to retained MQTT topic to restore state on startup."""
        async def on_message(_topic, payload):
            try:
                data = json.loads(payload)
                if isinstance(data, dict):
                    if "energy" in data:
                        self._energy_consumed_Wh = float(data["energy"])
                        _LOGGER.info(
                            "Restored energy state for %s: %.4f Wh",
                            self._id, self._energy_consumed_Wh
                        )
                    if "water" in data:
                        self._water_consumed_L = float(data["water"])
                        _LOGGER.info(
                            "Restored water state for %s: %.4f L",
                            self._id, self._water_consumed_L
                        )
            except Exception as e:
                _LOGGER.warning("Failed to restore state for %s: %s", self._id, e)
            finally:
                await self._message_bus.unsubscribe_and_stop_listen(self._sensor_topic)
        
        if self._message_bus is not None:
            asyncio.create_task(
                self._message_bus.subscribe_and_listen(self._sensor_topic, on_message)
            )

    def get_current_power(self) -> float:
        """Get current power usage in W (0 if output is OFF)."""
        if self._sensor_type != "power":
            return 0.0
        return (self._power_usage or 0.0) if self._output.state == ON else 0.0

    def get_total_energy(self) -> float:
        """Get total energy consumed in Wh."""
        return round(self._energy_consumed_Wh, 3)

    def get_current_flow_rate(self) -> float:
        """Get current flow rate in L/h (0 if output is OFF)."""
        if self._sensor_type != "water":
            return 0.0
        return (self._flow_rate or 0.0) if self._output.state == ON else 0.0

    def get_total_water(self) -> float:
        """Get total water consumed in L."""
        return round(self._water_consumed_L, 3)

    def _send_state(self):
        """Send current state to MQTT and EventBus (for WebSocket/frontend)."""
        payload = {}
        timestamp = int(time.time())
        
        if self._sensor_type == "power":
            payload["power"] = self.get_current_power()
            payload["energy"] = self.get_total_energy()
            
            # Send SensorEvents to frontend via EventBus
            self._event_bus.trigger_event(SensorEvent(
                entity_id=f"{self._id}_power",
                state=SensorState(
                    id=f"{self._id}_power",
                    name=f"{self._name} Power",
                    state=self.get_current_power(),
                    unit="W",
                    timestamp=timestamp,
                )
            ))
            self._event_bus.trigger_event(SensorEvent(
                entity_id=f"{self._id}_energy",
                state=SensorState(
                    id=f"{self._id}_energy",
                    name=f"{self._name} Energy",
                    state=self.get_total_energy(),
                    unit="Wh",
                    timestamp=timestamp,
                )
            ))
        elif self._sensor_type == "water":
            payload["volume_flow_rate"] = self.get_current_flow_rate()
            payload["water"] = self.get_total_water()
            
            # Send SensorEvents to frontend via EventBus
            self._event_bus.trigger_event(SensorEvent(
                entity_id=f"{self._id}_flow",
                state=SensorState(
                    id=f"{self._id}_flow",
                    name=f"{self._name} Flow Rate",
                    state=self.get_current_flow_rate(),
                    unit="L/h",
                    timestamp=timestamp,
                )
            ))
            self._event_bus.trigger_event(SensorEvent(
                entity_id=f"{self._id}_water",
                state=SensorState(
                    id=f"{self._id}_water",
                    name=f"{self._name} Water",
                    state=self.get_total_water(),
                    unit="L",
                    timestamp=timestamp,
                )
            ))
        
        self._message_bus.send_message(
            topic=self._sensor_topic,
            payload=payload,
            retain=True,
        )
        _LOGGER.debug("Sent state for %s: %s", self._id, payload)
