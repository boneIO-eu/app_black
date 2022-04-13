"""Helper dir for DS2482."""
from boneio.helper.ds2482.ds2482 import DS2482, DS2482_ADDRESS
from boneio.helper.ds2482.onewire import OneWire, OneWireBus


def ds_address(rom: bytes) -> int:
    return int.from_bytes(rom, "little")


__all__ = ["DS2482", "OneWire", "OneWireBus", "ds_address", "DS2482_ADDRESS"]
