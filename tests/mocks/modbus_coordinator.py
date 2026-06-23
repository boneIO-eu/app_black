"""Mock Modbus Coordinator for testing.

Redirects imports to the core boneio.modbus.mock_coordinator module.
"""

from boneio.modbus.mock_coordinator import (
    MockModbusCoordinator,
    MockModbusEntity,
    _find_device_json,
)
