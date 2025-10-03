from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel
from typing import TypedDict


class InputState(BaseModel):
    """Input state model."""
    name: str
    state: str
    type: str
    pin: str
    timestamp: float
    boneio_input: str

class InputsResponse(BaseModel):
    """Inputs response model."""
    inputs: list[InputState]

class OutputState(BaseModel):
    """Output state model."""
    id: str
    name: str
    state: str
    type: str
    expander_id: str | None
    pin: int
    timestamp: float | None = None

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

class HostSensorState(BaseModel):
    """Host Sensor state model."""
    id: str
    name: str
    state: str
    timestamp: float | None = None

class OutputsResponse(BaseModel):
    """Outputs response model."""
    outputs: list[OutputState]

class CoverResponse(BaseModel):
    """Cover response model."""
    covers: list[CoverState]

class StateUpdate(BaseModel):
    """State update model for WebSocket messages."""
    type: str  # 'input' or 'output' or 'cover'
    data: InputState | OutputState | SensorState | CoverState

class PositionDict(TypedDict, total=False):
    position: int
    tilt: int