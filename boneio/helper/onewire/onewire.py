"""OneWire base class for DS2482.
Module by https://github.com/fgervais/ds2482
"""
import adafruit_onewire.bus
from onewireio import OneWire as OneWireIO
from boneio.helper.onewire import DS2482
from typing import List
from adafruit_onewire.bus import OneWireAddress as AdafruitOneWireAddress


def ds_address(rom: bytes) -> int:
    return int.from_bytes(rom, "little")


def reverse_dallas_id(a: str) -> str:
    """Reverse sensor address."""
    return "".join(reversed([a[i : i + 2] for i in range(0, len(a), 2)]))


class OneWireAddress(AdafruitOneWireAddress):
    @property
    def int_address(self) -> int:
        return ds_address(self.rom)

    @property
    def hex_id(self) -> str:
        return reverse_dallas_id(self.rom.hex())

    @property
    def hw_id(self) -> str:
        return self.hex_id[2:-2]


class OneWire(OneWireIO):
    def __init__(self, ds2482: DS2482):
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
    def __init__(self, ds2482: DS2482):
        self._ow = OneWire(ds2482)
        self._readbit = self._ow.read_bit
        self._writebit = self._ow.write_bit
        self._maximum_devices = adafruit_onewire.bus._MAX_DEV

    def scan(self) -> List[OneWireAddress]:
        """Scan for devices on the bus and return a list of addresses."""
        devices = []
        diff = 65
        rom = None
        count = 0
        for _ in range(0xFF):
            rom, diff = self._search_rom(rom, diff)
            if rom:
                count += 1
                if count > self.maximum_devices:
                    raise RuntimeError(
                        "Maximum device count of {} exceeded.".format(
                            self.maximum_devices
                        )
                    )
                devices.append(OneWireAddress(rom))
            if diff == 0:
                break
        return devices
