"""OneWire base class for DS2482.
Module by https://github.com/fgervais/ds2482
"""
import adafruit_onewire.bus
from onewireio import OneWire as OneWireIO


class OneWire(OneWireIO):
    def __init__(self, ds2482):
        self.ds2482 = ds2482

    def deinit(self):
        """
        Deinitialize the OneWire bus and release any hardware resources for reuse.
        """
        self.ds2482.device_reset()

    def reset(self):
        """
        Reset the OneWire bus and read presence

        :return: False when at least one device is present
        """
        return self.ds2482.reset()

    def read_bit(self):
        """
        Read in a bit
        """
        return self.ds2482.single_bit()

    def write_bit(self, value):
        """
        Write out a bit based on value.
        """
        self.ds2482.single_bit(value)


class OneWireBus(adafruit_onewire.bus.OneWireBus):
    def __init__(self, ds2482):
        self._ow = OneWire(ds2482)
        self._readbit = self._ow.read_bit
        self._writebit = self._ow.write_bit
        self._maximum_devices = adafruit_onewire.bus._MAX_DEV
