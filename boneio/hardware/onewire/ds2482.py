"""DS2482 I2C to 1-Wire bridge driver using smbus2.

This module provides a native implementation of the DS2482 I2C to 1-Wire bridge
using smbus2, replacing the Adafruit CircuitPython library.

The DS2482 is an I2C to 1-Wire bridge that allows communication with 1-Wire devices
(like DS18B20 temperature sensors) over I2C.

Based on: https://github.com/fgervais/ds2482
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.hardware.i2c.bus import SMBus2I2C

_LOGGER = logging.getLogger(__name__)

# Default I2C address (AD0 = GND, AD1 = GND)
DS2482_ADDRESS = 0x18

# DS2482 device commands
COMMAND_DEVICE_RESET = 0xF0
COMMAND_SET_POINTER = 0xE1
COMMAND_WRITE_CONFIG = 0xD2
COMMAND_1W_RESET = 0xB4
COMMAND_1W_SINGLE_BIT = 0x87
COMMAND_1W_WRITE_BYTE = 0xA5
COMMAND_1W_READ_BYTE = 0x96
COMMAND_1W_TRIPLET = 0x78

# DS2482 read pointer codes
POINTER_STATUS = 0xF0
POINTER_DATA = 0xE1
POINTER_CONFIG = 0xC3

# DS2482 configuration register
CONFIG_ACTIVE_PULLUP = 0x01
CONFIG_STRONG_PULLUP = 0x04
CONFIG_1W_OVERDRIVE = 0x08
CONFIG_MASK = 0x0F

# DS2482 status register
STATUS_1W_BUSY = 0x01
STATUS_PRESENCE_PULSE = 0x02
STATUS_SHORT_DETECTED = 0x04
STATUS_LOGIC_LEVEL = 0x08
STATUS_DEVICE_RESET = 0x10
STATUS_SINGLE_BIT = 0x20
STATUS_TRIPLET_BIT = 0x40
STATUS_BRANCH_TAKEN = 0x80


class DS2482:
    """DS2482 I2C to 1-Wire bridge driver.
    
    This implementation uses smbus2 for direct I2C communication,
    replacing the Adafruit CircuitPython library.
    
    The DS2482 provides a bridge between I2C and 1-Wire protocols,
    allowing communication with 1-Wire devices (like temperature sensors)
    over I2C.
    
    Example:
        >>> from boneio.hardware.i2c.bus import SMBus2I2C
        >>> from boneio.hardware.onewire import DS2482
        >>> 
        >>> i2c = SMBus2I2C(bus_num=2)
        >>> ds = DS2482(i2c=i2c, address=0x18, active_pullup=False)
        >>> 
        >>> # Reset 1-Wire bus
        >>> presence = ds.reset()
        >>> if not presence:
        >>>     print("Device present on 1-Wire bus")
    """

    def __init__(
        self,
        i2c: SMBus2I2C,
        address: int = DS2482_ADDRESS,
        active_pullup: bool = False,
    ) -> None:
        """Initialize DS2482.
        
        Args:
            i2c: I2C bus instance (SMBus2I2C)
            address: I2C address of the device (default 0x18)
            active_pullup: Enable active pullup on 1-Wire bus
        """
        self._i2c = i2c
        self._address = address
        
        # Reset device
        self.device_reset()
        
        # Configure active pullup if requested
        if active_pullup:
            self.device_config = CONFIG_ACTIVE_PULLUP
        
        # Track 1-Wire bus busy time (for STRONG_PULLUP)
        self._bus_busy = time.monotonic()
        
        _LOGGER.debug(
            "Initialized DS2482 at address 0x%02X (active_pullup=%s)",
            address,
            active_pullup,
        )

    def device_reset(self) -> None:
        """Terminate any 1-Wire communication and reset the DS2482."""
        try:
            self._i2c.write_byte(self._address, COMMAND_DEVICE_RESET)
            _LOGGER.debug("DS2482 0x%02X: Device reset", self._address)
        except Exception as e:
            _LOGGER.error(
                "Failed to reset DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    @property
    def device_status(self) -> int:
        """Read device status register.
        
        Returns:
            Status register value
        """
        try:
            # Set pointer to status register
            self._i2c.write_i2c_block_data(
                self._address,
                COMMAND_SET_POINTER,
                [POINTER_STATUS],
            )
            # Read status
            status = self._i2c.read_byte(self._address)
            _LOGGER.debug(
                "DS2482 0x%02X: Status = 0x%02X",
                self._address,
                status,
            )
            return status
        except Exception as e:
            _LOGGER.error(
                "Failed to read status from DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    @property
    def device_config(self) -> int:
        """Read device configuration register.
        
        Returns:
            Configuration register value (4 bits)
        """
        try:
            # Set pointer to config register
            self._i2c.write_i2c_block_data(
                self._address,
                COMMAND_SET_POINTER,
                [POINTER_CONFIG],
            )
            # Read config
            config = self._i2c.read_byte(self._address) & 0x0F
            _LOGGER.debug(
                "DS2482 0x%02X: Config = 0x%02X",
                self._address,
                config,
            )
            return config
        except Exception as e:
            _LOGGER.error(
                "Failed to read config from DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    @device_config.setter
    def device_config(self, config: int) -> None:
        """Write device configuration register.
        
        Args:
            config: Configuration value (4 bits)
        """
        try:
            # Config byte format: [config (4 bits) | ~config (4 bits)]
            config_byte = (config & 0x0F) | ((~config << 4) & 0xF0)
            self._i2c.write_i2c_block_data(
                self._address,
                COMMAND_WRITE_CONFIG,
                [config_byte],
            )
            _LOGGER.debug(
                "DS2482 0x%02X: Set config to 0x%02X",
                self._address,
                config,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to write config to DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    def reset(self) -> bool:
        """Reset the 1-Wire bus and check for device presence.
        
        Returns:
            True if no device present, False if device present
        """
        try:
            # Send 1-Wire reset command
            self._i2c.write_byte(self._address, COMMAND_1W_RESET)
            
            # Wait for operation to complete
            while True:
                status = self._i2c.read_byte(self._address)
                if not (status & STATUS_1W_BUSY):
                    break
                time.sleep(0.001)
            
            # Check presence pulse (inverted logic: 0 = present)
            presence = not (status & STATUS_PRESENCE_PULSE)
            
            _LOGGER.debug(
                "DS2482 0x%02X: 1-Wire reset, presence=%s",
                self._address,
                presence,
            )
            
            return not presence  # Return True if no device
        except Exception as e:
            _LOGGER.error(
                "Failed to reset 1-Wire bus on DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    def single_bit(
        self,
        bit: int = 1,
        strong_pullup: bool = False,
        busy: float | None = None,
    ) -> bool:
        """Write and read a single bit on the 1-Wire bus.
        
        Args:
            bit: Bit value to write (0 or 1)
            strong_pullup: Enable strong pullup after operation
            busy: Time in seconds to mark bus as busy
            
        Returns:
            Bit value read from bus
        """
        try:
            # Enable strong pullup if requested
            if strong_pullup:
                current_config = self.device_config
                new_config = current_config | CONFIG_STRONG_PULLUP
                self.device_config = new_config
            
            # Send single bit command
            bit_value = 0x80 if bit else 0x00
            self._i2c.write_i2c_block_data(
                self._address,
                COMMAND_1W_SINGLE_BIT,
                [bit_value],
            )
            
            # Wait for operation to complete
            while True:
                status = self._i2c.read_byte(self._address)
                if not (status & STATUS_1W_BUSY):
                    break
                time.sleep(0.001)
            
            # Mark bus as busy if requested
            if busy:
                self._bus_busy = time.monotonic() + busy
            
            # Return bit value read
            result = bool(status & STATUS_SINGLE_BIT)
            
            _LOGGER.debug(
                "DS2482 0x%02X: Single bit write=%d, read=%d",
                self._address,
                bit,
                result,
            )
            
            return result
        except Exception as e:
            _LOGGER.error(
                "Failed to write/read single bit on DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    def write_byte(
        self,
        data: int,
        strong_pullup: bool = False,
        busy: float | None = None,
    ) -> None:
        """Write a byte to the 1-Wire bus.
        
        Args:
            data: Byte value to write (0-255)
            strong_pullup: Enable strong pullup after operation
            busy: Time in seconds to mark bus as busy
        """
        try:
            # Enable strong pullup if requested
            if strong_pullup:
                current_config = self.device_config
                new_config = current_config | CONFIG_STRONG_PULLUP
                self.device_config = new_config
            
            # Send write byte command
            self._i2c.write_i2c_block_data(
                self._address,
                COMMAND_1W_WRITE_BYTE,
                [data],
            )
            
            # Wait for operation to complete
            while True:
                status = self._i2c.read_byte(self._address)
                if not (status & STATUS_1W_BUSY):
                    break
                time.sleep(0.001)
            
            # Mark bus as busy if requested
            if busy:
                self._bus_busy = time.monotonic() + busy
            
            _LOGGER.debug(
                "DS2482 0x%02X: Wrote byte 0x%02X",
                self._address,
                data,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to write byte to DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    def read_byte(self) -> int:
        """Read a byte from the 1-Wire bus.
        
        Returns:
            Byte value read (0-255)
        """
        try:
            # Send read byte command
            self._i2c.write_byte(self._address, COMMAND_1W_READ_BYTE)
            
            # Wait for operation to complete
            while True:
                status = self._i2c.read_byte(self._address)
                if not (status & STATUS_1W_BUSY):
                    break
                time.sleep(0.001)
            
            # Set pointer to data register
            self._i2c.write_i2c_block_data(
                self._address,
                COMMAND_SET_POINTER,
                [POINTER_DATA],
            )
            
            # Read data
            data = self._i2c.read_byte(self._address)
            
            _LOGGER.debug(
                "DS2482 0x%02X: Read byte 0x%02X",
                self._address,
                data,
            )
            
            return data
        except Exception as e:
            _LOGGER.error(
                "Failed to read byte from DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    def wait_ready(self) -> int:
        """Wait for the 1-Wire bus to be ready.
        
        Returns:
            Status register value
        """
        try:
            # Wait for bus busy time to expire
            while True:
                t = self._bus_busy - time.monotonic()
                if t > 0:
                    time.sleep(t)
                else:
                    break
            
            # Set pointer to status register
            self._i2c.write_i2c_block_data(
                self._address,
                COMMAND_SET_POINTER,
                [POINTER_STATUS],
            )
            
            # Wait for device to be ready
            while True:
                status = self._i2c.read_byte(self._address)
                if not (status & STATUS_1W_BUSY):
                    break
                time.sleep(0.001)
            
            _LOGGER.debug(
                "DS2482 0x%02X: Ready, status=0x%02X",
                self._address,
                status,
            )
            
            return status
        except Exception as e:
            _LOGGER.error(
                "Failed to wait for ready on DS2482 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    def triplet(self, direction: int) -> tuple[int, int, int]:
        """Perform a 1-Wire triplet operation (search algorithm).
        
        Args:
            direction: Search direction bit
            
        Returns:
            Tuple of (id_bit, cmp_id_bit, direction_taken)
        """
        # Not implemented in original code
        raise NotImplementedError("Triplet operation not implemented")
