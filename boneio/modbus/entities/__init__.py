"""Modbus entities - sensors, switches, and other device entities."""

from boneio.modbus.entities.base import BaseEntity, ModbusBaseEntity, ModbusDerivedEntity
from boneio.modbus.entities.sensor.binary import ModbusBinarySensor
from boneio.modbus.entities.sensor.numeric import ModbusNumericSensor
from boneio.modbus.entities.sensor.text import ModbusTextSensor
from boneio.modbus.entities.writeable.binary import ModbusBinaryWriteableEntityDiscrete
from boneio.modbus.entities.writeable.numeric import (
    ModbusNumericWriteableEntity,
    ModbusNumericWriteableEntityDiscrete,
)
from boneio.modbus.entities.derived.numeric import ModbusDerivedNumericSensor
from boneio.modbus.entities.derived.select import ModbusDerivedSelect
from boneio.modbus.entities.derived.switch import ModbusDerivedSwitch
from boneio.modbus.entities.derived.text import ModbusDerivedTextSensor

__all__ = [
    # Base classes
    "BaseEntity",
    "ModbusBaseEntity",
    "ModbusDerivedEntity",
    # Sensors (read-only)
    "ModbusBinarySensor",
    "ModbusNumericSensor",
    "ModbusTextSensor",
    # Writeable
    "ModbusBinaryWriteableEntityDiscrete",
    "ModbusNumericWriteableEntity",
    "ModbusNumericWriteableEntityDiscrete",
    # Derived
    "ModbusDerivedNumericSensor",
    "ModbusDerivedSelect",
    "ModbusDerivedSwitch",
    "ModbusDerivedTextSensor",
]

