"""Sensor module."""
from boneio.sensor.adc import GpioADCSensor, initialize_adc
from boneio.sensor.gpio import GpioInputBinarySensor as GpioInputBinarySensorOld
from boneio.sensor.gpio_new import GpioInputBinarySensorNew
from boneio.sensor.temp.dallas import DallasSensorDS2482
from boneio.sensor.temp.lm75 import LM75Sensor
from boneio.sensor.temp.mcp9808 import MCP9808Sensor
from boneio.sensor.ina219 import INA219

__all__ = [
    "DallasSensorDS2482",
    "LM75Sensor",
    "MCP9808Sensor",
    "GpioInputBinarySensorOld",
    "GpioInputBinarySensorNew",
    "initialize_adc",
    "GpioADCSensor",
    "INA219"
]
