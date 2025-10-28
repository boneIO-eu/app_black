"""Analog hardware drivers.

This module provides drivers for analog interfaces:
- BeagleBone Black ADC (using Linux IIO subsystem)
"""

from boneio.hardware.analog.adc import ADCReader, GpioADCSensor, initialize_adc

__all__ = [
    "ADCReader",
    "GpioADCSensor",
    "initialize_adc",
]
