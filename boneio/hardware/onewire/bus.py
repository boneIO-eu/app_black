"""OneWire bus implementation using DS2482.

This module provides a native implementation of the OneWire bus protocol
without dependencies on Adafruit CircuitPython libraries.

Based on: https://github.com/fgervais/ds2482
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.hardware.onewire.ds2482 import DS2482

_LOGGER = logging.getLogger(__name__)

# Maximum number of devices on 1-Wire bus
_MAX_DEVICES = 20


def ds_address(rom: bytes | bytearray) -> int:
    """Convert ROM bytes to integer address.
    
    Args:
        rom: 8-byte ROM address
        
    Returns:
        Integer representation of address
    """
    return int.from_bytes(rom, "little")


def reverse_dallas_id(address: str) -> str:
    """Reverse Dallas/Maxim sensor address format.
    
    Args:
        address: Hex string address (e.g., "28FF123456789ABC")
        
    Returns:
        Reversed address (e.g., "BC9A78563412FF28")
    """
    return "".join(reversed([address[i : i + 2] for i in range(0, len(address), 2)]))


class OneWireAddress:
    """Represents a 1-Wire device address.
    
    Provides various formats for the 64-bit ROM address.
    """

    def __init__(self, rom: bytearray) -> None:
        """Initialize OneWireAddress.
        
        Args:
            rom: 8-byte ROM address
        """
        self.rom = rom

    @property
    def int_address(self) -> int:
        """Get integer representation of address.
        
        Returns:
            Integer address
        """
        return ds_address(self.rom)

    @property
    def hex_id(self) -> str:
        """Get hex string representation (reversed).
        
        Returns:
            Hex string (e.g., "28FF123456789ABC")
        """
        return reverse_dallas_id(self.rom.hex())

    @property
    def hw_id(self) -> str:
        """Get hardware ID (hex_id without family code and CRC).
        
        Returns:
            Hardware ID string
        """
        return self.hex_id[2:-2]

    def __repr__(self) -> str:
        """String representation."""
        return f"OneWireAddress({self.hex_id})"

    def __eq__(self, other: object) -> bool:
        """Compare addresses."""
        if not isinstance(other, OneWireAddress):
            return False
        return self.rom == other.rom

    def __hash__(self) -> int:
        """Hash for use in sets/dicts."""
        return hash(bytes(self.rom))


class OneWire:
    """Low-level OneWire protocol implementation using DS2482.
    
    Provides basic read/write bit operations on the 1-Wire bus.
    """

    def __init__(self, ds2482: DS2482) -> None:
        """Initialize OneWire.
        
        Args:
            ds2482: DS2482 bridge instance
        """
        self.ds2482 = ds2482

    def deinit(self) -> None:
        """Deinitialize the OneWire bus and release hardware resources."""
        self.ds2482.device_reset()
        _LOGGER.debug("OneWire bus deinitialized")

    def reset(self) -> bool:
        """Reset the OneWire bus and check for device presence.
        
        Returns:
            False when at least one device is present, True if no device
        """
        return self.ds2482.reset()

    def read_bit(self) -> bool:
        """Read a single bit from the bus.
        
        Returns:
            Bit value (True or False)
        """
        return self.ds2482.single_bit()

    def write_bit(self, value: bool) -> None:
        """Write a single bit to the bus.
        
        Args:
            value: Bit value to write
        """
        self.ds2482.single_bit(1 if value else 0)


class OneWireBus:
    """High-level OneWire bus with device search capability.
    
    Implements the 1-Wire search algorithm to discover devices on the bus.
    """

    def __init__(self, ds2482: DS2482) -> None:
        """Initialize OneWireBus.
        
        Args:
            ds2482: DS2482 bridge instance
        """
        self._ow = OneWire(ds2482)
        self._readbit = self._ow.read_bit
        self._writebit = self._ow.write_bit
        self._maximum_devices = _MAX_DEVICES

    @property
    def maximum_devices(self) -> int:
        """Get maximum number of devices allowed on bus.
        
        Returns:
            Maximum device count
        """
        return self._maximum_devices

    def scan(self) -> list[OneWireAddress]:
        """Scan for devices on the bus and return a list of addresses.
        
        Returns:
            List of OneWireAddress objects
            
        Raises:
            RuntimeError: If maximum device count exceeded
        """
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
                        f"Maximum device count of {self.maximum_devices} exceeded."
                    )
                devices.append(OneWireAddress(rom))
            if diff == 0:
                break
        
        _LOGGER.debug("OneWire scan found %d devices", len(devices))
        return devices

    def _search_rom(
        self,
        rom: bytearray | None,
        diff: int,
    ) -> tuple[bytearray | None, int]:
        """Perform 1-Wire search algorithm.
        
        This implements the standard 1-Wire search algorithm to discover
        device ROM addresses on the bus.
        
        Args:
            rom: Previous ROM address (or None for first search)
            diff: Last discrepancy position from previous search
            
        Returns:
            Tuple of (rom_address, last_discrepancy)
        """
        if not self._ow.reset():
            return None, 0
        
        self._writebit(True)  # Search ROM command (0xF0)
        self._writebit(False)
        self._writebit(False)
        self._writebit(False)
        self._writebit(True)
        self._writebit(True)
        self._writebit(True)
        self._writebit(True)
        
        if not rom:
            rom = bytearray(8)
        
        last_zero = 0
        
        for i in range(64):
            # Read two bits: id_bit and cmp_id_bit
            id_bit = self._readbit()
            cmp_id_bit = self._readbit()
            
            if id_bit and cmp_id_bit:
                # No devices responded
                return None, 0
            elif not id_bit and not cmp_id_bit:
                # Discrepancy - both 0 and 1 present
                if i < diff:
                    # Take same path as before
                    search_direction = bool((rom[i // 8] >> (i % 8)) & 1)
                elif i == diff:
                    # Take 1 path at last discrepancy
                    search_direction = True
                else:
                    # Take 0 path for new discrepancies
                    search_direction = False
                
                if not search_direction:
                    last_zero = i
            else:
                # All devices have same bit at this position
                search_direction = id_bit
            
            # Write direction bit
            self._writebit(search_direction)
            
            # Update ROM
            byte_index = i // 8
            bit_index = i % 8
            if search_direction:
                rom[byte_index] |= 1 << bit_index
            else:
                rom[byte_index] &= ~(1 << bit_index)
        
        return rom, last_zero

    def reset(self) -> bool:
        """Reset the OneWire bus.
        
        Returns:
            False if device present, True if no device
        """
        return self._ow.reset()

    def read_byte(self) -> int:
        """Read a byte from the bus.
        
        Returns:
            Byte value (0-255)
        """
        byte = 0
        for i in range(8):
            if self._readbit():
                byte |= 1 << i
        return byte

    def write_byte(self, byte: int) -> None:
        """Write a byte to the bus.
        
        Args:
            byte: Byte value to write (0-255)
        """
        for i in range(8):
            self._writebit(bool((byte >> i) & 1))

    def select(self, address: OneWireAddress) -> None:
        """Select a specific device on the bus.
        
        Args:
            address: Device address to select
        """
        self.reset()
        # Match ROM command (0x55)
        self.write_byte(0x55)
        # Write 64-bit ROM address
        for byte in address.rom:
            self.write_byte(byte)

    def skip_rom(self) -> None:
        """Skip ROM selection (address all devices).
        
        Useful when only one device is on the bus.
        """
        self.reset()
        # Skip ROM command (0xCC)
        self.write_byte(0xCC)
