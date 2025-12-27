"""Event models for EventBus.

Events represent things that happened in the system.
They carry context about the event and the state of the entity.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from boneio.const import ClickTypes
from boneio.models.state import (
    CoverState,
    GroupState,
    HostSensorState,
    InputState,
    ModbusDeviceState,
    OutputState,
    SensorState,
)


class InputEvent(BaseModel):
    """Input event - triggered when an input detects a click/press.
    
    Attributes:
        event_type: Type of event (always "input")
        entity_id: Unique input identifier
        click_type: Type of click (single, double, long, pressed, released)
        duration: Duration of the press in seconds (optional)
        state: Current state of the input
        publish_only: If True, only publish to MQTT without executing actions
    """
    
    event_type: Literal["input"] = "input"
    entity_id: str
    click_type: ClickTypes | None = None
    duration: float | None = None
    state: InputState
    publish_only: bool = False


class OutputEvent(BaseModel):
    """Output event - triggered when output state changes.
    
    Attributes:
        event_type: Type of event (always "output")
        entity_id: Unique output identifier
        state: Current state of the output
    """
    
    event_type: Literal["output"] = "output"
    entity_id: str
    state: OutputState


class CoverEvent(BaseModel):
    """Cover event - triggered when cover state changes.
    
    Attributes:
        event_type: Type of event (always "cover")
        entity_id: Unique cover identifier
        state: Current state of the cover
    """
    
    event_type: Literal["cover"] = "cover"
    entity_id: str
    state: CoverState


class SensorEvent(BaseModel):
    """Sensor event - triggered when sensor value changes.
    
    Attributes:
        event_type: Type of event (always "sensor")
        entity_id: Unique sensor identifier
        state: Current sensor state and value
    """
    
    event_type: Literal["sensor"] = "sensor"
    entity_id: str
    state: SensorState


class ModbusDeviceEvent(BaseModel):
    """Modbus device event - triggered when a modbus device state changes.
    
    Attributes:
        event_type: Type of event (always "modbus_device")
        entity_id: Unique modbus device identifier
        state: Current state of the device (represented as SensorState)
    """
    
    event_type: Literal["modbus_device"] = "modbus_device"
    entity_id: str
    state: ModbusDeviceState


class HostEvent(BaseModel):
    """Host event - triggered when host system information changes.
    
    Attributes:
        event_type: Type of event (always "host")
        entity_id: Unique host sensor identifier
        state: Current state of the host sensor
    """
    
    event_type: Literal["host"] = "host"
    entity_id: str
    state: HostSensorState


class GroupEvent(BaseModel):
    """Output group event - triggered when group state changes.
    
    Attributes:
        event_type: Type of event (always "group")
        entity_id: Unique group identifier
        state: Current state of the group
    """
    
    event_type: Literal["group"] = "group"
    entity_id: str
    state: GroupState


class ConfigReloadEvent(BaseModel):
    """Config reload event - triggered when configuration is reloaded.
    
    Frontend should clear old states and wait for fresh data.
    
    Attributes:
        event_type: Type of event (always "config_reload")
        sections: List of reloaded section names
    """
    
    event_type: Literal["config_reload"] = "config_reload"
    sections: list[str]


class InputsReloadedEvent(BaseModel):
    """Inputs reloaded event - triggered after input configuration is reloaded.
    
    This event signals WebSocket handlers to re-send all input states to clients.
    
    Attributes:
        event_type: Type of event (always "inputs_reloaded")
    """
    
    event_type: Literal["inputs_reloaded"] = "inputs_reloaded"


# Discriminated union for all events
# The discriminator field "event_type" allows Pydantic to automatically
# determine which event type to use when parsing
Event = InputEvent | OutputEvent | CoverEvent | SensorEvent | ModbusDeviceEvent | HostEvent | GroupEvent | ConfigReloadEvent | InputsReloadedEvent

__all__ = [
    "InputEvent",
    "OutputEvent",
    "CoverEvent",
    "SensorEvent",
    "ModbusDeviceEvent",
    "HostEvent",
    "GroupEvent",
    "ConfigReloadEvent",
    "InputsReloadedEvent",
    "Event",
]

