"""1-Wire ROM addresses in the two forms people paste.

The kernel names a device ``28-000000053f33``: family code, then the 48-bit
serial. ESPHome writes the whole 64-bit ROM as one number,
``0xc0000000053f3328``: CRC in the top byte, the same serial, the family in
the bottom byte. Both are accepted in ``config.yaml``; a valid address
reaches the rest of boneIO in the kernel form, lower case, as sysfs
spells it.
"""

from __future__ import annotations

import re
from typing import Any

_KERNEL = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{12})$")
_ESPHOME = re.compile(r"^0x([0-9a-f]{16})$")
_BARE_SERIAL = re.compile(r"^[0-9a-f]{12}$")


def _crc8(data: bytes) -> int:
    """Maxim/Dallas CRC-8 (polynomial x^8 + x^5 + x^4 + 1, reflected)."""
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 1
            crc >>= 1
            if mix:
                crc ^= 0x8C
            byte >>= 1
    return crc


def _rom(family: str, serial: str) -> bytes:
    """The ROM bytes in wire order: family, serial least significant first."""
    return bytes([int(family, 16)]) + bytes.fromhex(serial)[::-1]


def kernel_address(value: str | int) -> str:
    """Return ``ff-ssssssssssss`` for an address in either form.

    A bare 12-digit serial is taken as a DS18B20 (family 28), as before.
    Raises ValueError for anything else, and for an ESPHome address whose
    CRC byte does not match: that is a typo, not a sensor.
    """
    if isinstance(value, bool):
        raise ValueError(f"not a 1-Wire address: {value!r}")
    if isinstance(value, int):
        # YAML reads an unquoted 0x... as a number.
        text = f"0x{value:016x}"
    else:
        text = str(value).strip().lower()
    if _BARE_SERIAL.match(text):
        return f"28-{text}"
    if _KERNEL.match(text):
        return text
    if m := _ESPHOME.match(text):
        rom = m.group(1)
        crc, serial, family = rom[:2], rom[2:14], rom[14:]
        if _crc8(_rom(family, serial)) != int(crc, 16):
            raise ValueError(f"1-Wire address {text}: CRC byte does not match the rest")
        return f"{family}-{serial}"
    raise ValueError(
        f"not a 1-Wire address: {value!r} (expected 28-0000098c7df0 or 0x...28)"
    )


def loaded_address(value: Any) -> Any:
    """The kernel form where there is one, anything else as it was.

    For loading config.yaml: an address that was never valid keeps loading
    as before, and its sensor waits on the bus, instead of the whole
    controller refusing to start. Saves are checked by kernel_address.
    """
    try:
        return kernel_address(value)
    except ValueError:
        return value


def kernel_addresses(sensors: Any) -> Any:
    """The ``sensor`` section with every address passed through loaded_address."""
    if not isinstance(sensors, list):
        return sensors
    return [
        {**s, "address": loaded_address(s["address"])}
        if isinstance(s, dict) and "address" in s
        else s
        for s in sensors
    ]


def esphome_address(value: str | int) -> str:
    """Return the ESPHome ``0x...`` form of an address in either form."""
    family, serial = kernel_address(value).split("-")
    return f"0x{_crc8(_rom(family, serial)):02x}{serial}{family}"
