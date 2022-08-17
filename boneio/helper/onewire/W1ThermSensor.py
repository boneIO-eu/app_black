"""Custom W1ThermSensor class to support hex addressing of W1 sensors.
"""
from typing import List
from w1thermsensor import AsyncW1ThermSensor, Sensor
from boneio.helper.onewire import OneWireAddress, reverse_dallas_id


def crc82(data: bytearray) -> int:
    """
    Perform the 1-Wire CRC check on the provided data. Function from Circuit Python Adafruit.

    :param bytearray data: 8 byte array representing 64 bit ROM code
    """
    crc = 0

    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x01:
                crc = (crc >> 1) ^ 0x8C
            else:
                crc >>= 1
            crc &= 0xFF
    return crc


class AsyncBoneIOW1ThermSensor(AsyncW1ThermSensor):
    def __init__(self, *args, **kwargs):  # pragma: no cover
        """Custom init function to work with same addressing type as esphome."""
        self._ds18b20_str_id = hex(Sensor.DS18B20)[2:]
        try:
            sensor_id = kwargs.pop("sensor_id")
            if type(sensor_id) == OneWireAddress:
                sensor_id = sensor_id.hw_id
            super().__init__(*args, **kwargs, sensor_id=sensor_id)
        except KeyError:
            super().__init__(*args, **kwargs)
        _crc = crc82(
            bytes.fromhex(f"{self._ds18b20_str_id}{reverse_dallas_id(self.id)}")
        )
        self._hex_id = f"{hex(_crc)}{self.id}{self._ds18b20_str_id}".lower()

    @classmethod
    def scan(cls) -> List["OneWireAddress"]:
        """Return only DS18B20 sensors. Add more sensors in the future."""

        def is_sensor(dir_name):
            return dir_name.startswith(hex(Sensor.DS18B20)[2:])

        def get_hex(name):
            _hex_id = bytes.fromhex(f"{name[:2]}{reverse_dallas_id(name[3:])}")
            return _hex_id + bytes([crc82(_hex_id)])

        return [
            OneWireAddress(get_hex(name=s.name))
            for s in cls.BASE_DIRECTORY.iterdir()
            if is_sensor(s.name)
        ]

    @property
    def rom(self) -> bytes:
        """Get rom id."""
        return bytearray.fromhex(self.hex_id)

    @property
    def hex_id(self) -> str:
        """Get hex representation of sensor."""
        if not self._hex_id:
            _crc = crc82(
                bytes.fromhex(f"{self._ds18b20_str_id}{reverse_dallas_id(self.id)}")
            )
            self._hex_id = f"{hex(_crc)}{self.id}{self._ds18b20_str_id}".lower()
        return self._hex_id
