"""State models for BoneIO entities.

State models represent the current state of entities (inputs, outputs, covers, sensors).
These are used for:
- WebSocket messages to UI
- State persistence
- Home Assistant discovery
- API responses
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel


class InputState(BaseModel):
    """Input state model."""
    name: str
    state: str
    type: str
    pin: str
    timestamp: float
    boneio_input: str
    area: str | None = None
    remote: bool = False


class OutputState(BaseModel):
    """Output state model."""
    id: str
    name: str
    state: str
    type: str
    expander_id: str | None
    pin: str | None
    timestamp: float | None = None
    area: str | None = None
    interlock_groups: list[str] = []
    # Adjustable duration fields (optional, only present when feature is enabled)
    adjustable_duration: bool = False
    adjustable_duration_value: float | None = None
    duration_min: float | None = None
    duration_max: float | None = None
    duration_unit: str | None = None
    # Remote output flag
    remote: bool = False
    # Brightness (0-255) for dimmable lights
    brightness: int | None = None


class CoverState(BaseModel):
    """Cover state model."""
    id: str
    name: str
    state: str
    position: int
    current_operation: str
    timestamp: float | None = None
    tilt: int = 0  # Tilt position (0-100)
    kind: str


class SensorState(BaseModel):
    """Sensor state model."""
    id: str
    name: str
    state: float | str | None
    unit: str | None
    timestamp: float | None
    attributes: dict[str, float | str | int | bool | None] | None = None

class ModbusDeviceState(BaseModel):
    """Modbus device state model."""
    id: str
    name: str
    state: float | str | None
    unit: str | None
    timestamp: float | None
    device_group: str
    coordinator_id: str  # Coordinator ID for API calls
    entity_type: str
    x_mapping: dict[str, str] | None = None  # Value mapping for select/switch (e.g., {"1": "Auto", "2": "Cool"})
    payload_on: str | None = None  # For switch entities
    payload_off: str | None = None  # For switch entities
    step: float | str | None = None  # Step value for numeric inputs
    custom_label: str | None = None  # User-defined custom label from YAML config

class HostSensorState(BaseModel):
    """Host sensor state model."""
    id: str
    name: str
    state: str
    timestamp: float | None = None


class GroupState(BaseModel):
    """Output group state model."""
    id: str
    name: str
    state: str
    type: str
    timestamp: float | None = None


# Response models for API endpoints
class InputsResponse(BaseModel):
    """Inputs response model."""
    inputs: list[InputState]


class OutputsResponse(BaseModel):
    """Outputs response model."""
    outputs: list[OutputState]


class CoverResponse(BaseModel):
    """Cover response model."""
    covers: list[CoverState]


# Utility types
class PositionDict(TypedDict, total=False):
    """Position dictionary for covers — used for API/MQTT/WebUI (rounded int values)."""
    position: int
    tilt: int


class SavedPositionDict(TypedDict, total=False):
    """Position dictionary for covers — used for disk persistence (full float precision)."""
    position: float
    tilt: float


__all__ = [
    # State models
    "InputState",
    "OutputState",
    "CoverState",
    "SensorState",
    "HostSensorState",
    "GroupState",
    # Response models
    "InputsResponse",
    "OutputsResponse",
    "CoverResponse",
    # Utility
    "PositionDict",
    "SavedPositionDict",
    "ModbusDeviceState",
]

