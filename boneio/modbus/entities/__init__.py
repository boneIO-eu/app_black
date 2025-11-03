"""Modbus entities - sensors, switches, and other device entities."""

from boneio.modbus.entities.base import BaseEntity, ModbusBaseEntity
# Backwards compatibility aliases
from boneio.modbus.entities.sensor.base import BaseSensor, ModbusBaseSensor
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

# Aliases for backwards compatibility
ModbusSensor = ModbusBaseSensor
BinarySensor = ModbusBinarySensor
NumericSensor = ModbusNumericSensor
TextSensor = ModbusTextSensor
BinaryWriteable = ModbusBinaryWriteableEntityDiscrete
NumericWriteable = ModbusNumericWriteableEntity
NumericDerived = ModbusDerivedNumericSensor
SelectDerived = ModbusDerivedSelect
SwitchDerived = ModbusDerivedSwitch
TextDerived = ModbusDerivedTextSensor

__all__ = [
    # Base classes (new names)
    "BaseEntity",
    "ModbusBaseEntity",
    # Base classes (backwards compatibility aliases)
    "BaseSensor",
    "ModbusBaseSensor",
    "ModbusSensor",  # Alias for ModbusBaseSensor
    # Sensors (read-only)
    "ModbusBinarySensor",
    "BinarySensor",  # Alias
    "ModbusNumericSensor",
    "NumericSensor",  # Alias
    "ModbusTextSensor",
    "TextSensor",  # Alias
    # Writeable
    "ModbusBinaryWriteableEntityDiscrete",
    "BinaryWriteable",  # Alias
    "ModbusNumericWriteableEntity",
    "ModbusNumericWriteableEntityDiscrete",
    "NumericWriteable",  # Alias
    # Derived
    "ModbusDerivedNumericSensor",
    "NumericDerived",  # Alias
    "ModbusDerivedSelect",
    "SelectDerived",  # Alias
    "ModbusDerivedSwitch",
    "SwitchDerived",  # Alias
    "ModbusDerivedTextSensor",
    "TextDerived",  # Alias
]

