"""Sensor module."""
from boneio.sensor.adc import GpioADCSensor, initialize_adc
from boneio.sensor.gpio import GpioInputBinarySensor
from boneio.sensor.gpio_beta import GpioInputBinarySensorBeta
from boneio.sensor.temp.dallas import DallasSensorDS2482
from boneio.sensor.temp.lm75 import LM75Sensor
from boneio.sensor.temp.mcp9808 import MCP9808Sensor

__all__ = [
    "DallasSensorDS2482",
    "LM75Sensor",
    "MCP9808Sensor",
    "GpioInputBinarySensor",
    "GpioInputBinarySensorBeta",
    "initialize_adc",
    "GpioADCSensor",
]
