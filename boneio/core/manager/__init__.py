"""Manager module - orchestrates all subsystems.

This module provides the main Manager class that coordinates:
- Outputs (relay, switch, light, led, valve)
- Inputs (event, binary_sensor)
- Covers (time-based, previous-state, venetian)
- Sensors (temperature, power, analog)
- Modbus (RTU/TCP devices)
- Display (OLED)
"""

from boneio.core.manager.covers import CoverManager
from boneio.core.manager.display import DisplayManager
from boneio.core.manager.inputs import InputManager
from boneio.core.manager.modbus import ModbusManager
from boneio.core.manager.outputs import OutputManager
from boneio.core.manager.sensors import SensorManager

__all__ = [
    "Manager",
    "OutputManager",
    "InputManager",
    "CoverManager",
    "SensorManager",
    "ModbusManager",
    "DisplayManager",
]

# Import Manager from separate file to avoid circular imports
from boneio.core.manager.manager import Manager  # noqa: E402

__all__.append("Manager")
