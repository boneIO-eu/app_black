"""BoneIO models package.

This package contains all Pydantic models used throughout BoneIO:
- state.py: State models for entities (InputState, OutputState, etc.)
- events.py: Event models for EventBus (InputEvent, OutputEvent, etc.)
- mqtt.py: MQTT-specific models
- logs.py: Logging models
- files.py: File handling models
"""

from __future__ import annotations
from pydantic import BaseModel

# Import State models from state.py
from boneio.models.state import (
    CoverResponse,
    CoverState,
    GroupState,
    HostSensorState,
    InputsResponse,
    InputState,
    OutputsResponse,
    OutputState,
    PositionDict,
    SensorState,
)

from boneio.models.events import Event

class StateUpdate(BaseModel):
    """State update model for WebSocket messages."""
    type: str  # 'input' or 'output' or 'cover' or 'sensor'
    data: InputState | OutputState | SensorState | CoverState | Event

# Event models are in events.py - import separately when needed:
# from boneio.models.events import InputEvent, OutputEvent, etc.

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
    "StateUpdate",
    # Utility
    "PositionDict",
]