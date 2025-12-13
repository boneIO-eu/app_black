"""PCA9685 I2C PWM driver using smbus2.

This module provides a native implementation of the PCA9685 16-channel,
12-bit PWM driver using smbus2, replacing the Adafruit CircuitPython library.

The PCA9685 is a 16-channel PWM controller with:
- 16 PWM outputs (channels 0-15)
- 12-bit resolution (0-4095)
- I2C interface
- Programmable frequency (40-1000 Hz)
- Internal 25 MHz oscillator

For BoneIO, we use PCA9685 for LED dimming and PWM-based relay control.

Register Map:
- MODE1 (0x00): Mode register 1
- MODE2 (0x01): Mode register 2
- LED0_ON_L to LED15_OFF_H (0x06-0x45): PWM channel registers
- PRESCALE (0xFE): PWM frequency prescaler

Each channel has 4 registers:
- LEDn_ON_L (low byte of ON time)
- LEDn_ON_H (high byte of ON time)
- LEDn_OFF_L (low byte of OFF time)
- LEDn_OFF_H (high byte of OFF time)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.hardware.i2c.bus import SMBus2I2C

_LOGGER = logging.getLogger(__name__)

# Minimum delay between I2C operations in seconds
# This prevents bus contention when switching multiple outputs rapidly
I2C_OPERATION_DELAY = 0.002  # 2ms

# Register addresses
MODE1 = 0x00
MODE2 = 0x01
SUBADR1 = 0x02
SUBADR2 = 0x03
SUBADR3 = 0x04
ALLCALLADR = 0x05
LED0_ON_L = 0x06
LED0_ON_H = 0x07
LED0_OFF_L = 0x08
LED0_OFF_H = 0x09
ALL_LED_ON_L = 0xFA
ALL_LED_ON_H = 0xFB
ALL_LED_OFF_L = 0xFC
ALL_LED_OFF_H = 0xFD
PRESCALE = 0xFE

# MODE1 bits
RESTART = 0x80
SLEEP = 0x10
ALLCALL = 0x01
EXTCLK = 0x40
AI = 0x20  # Auto-increment

# MODE2 bits
OUTDRV = 0x04
INVRT = 0x10


class PCAChannel:
    """Single PWM channel on PCA9685.
    
    This class provides an API compatible with Adafruit's PCAChannels
    for controlling individual PWM channels.
    """

    def __init__(self, channel: int, pca: PCA9685) -> None:
        """Initialize a PWM channel.
        
        Args:
            channel: Channel number (0-15)
            pca: Parent PCA9685 instance
        """
        self._channel = channel
        self._pca = pca

    @property
    def duty_cycle(self) -> int:
        """Get the PWM duty cycle (0-65535).
        
        The PCA9685 has 12-bit resolution (0-4095), but we scale it
        to 16-bit (0-65535) for compatibility with CircuitPython API.
        
        Returns:
            Duty cycle value (0-65535)
        """
        pwm = self._pca._read_channel(self._channel)
        # Scale from 12-bit (0-4095) to 16-bit (0-65535)
        return int(pwm * 65535 / 4095)

    @duty_cycle.setter
    def duty_cycle(self, value: int) -> None:
        """Set the PWM duty cycle (0-65535).
        
        Args:
            value: Duty cycle value (0-65535)
        """
        # Scale from 16-bit (0-65535) to 12-bit (0-4095)
        pwm = int(value * 4095 / 65535)
        self._pca._write_channel(self._channel, pwm)


class PCAChannels:
    """Container for all PWM channels on PCA9685.
    
    Provides array-like access to channels: pca.channels[0]
    """

    def __init__(self, pca: PCA9685) -> None:
        """Initialize channels container.
        
        Args:
            pca: Parent PCA9685 instance
        """
        self._pca = pca
        self._channels = [PCAChannel(i, pca) for i in range(16)]

    def __getitem__(self, index: int) -> PCAChannel:
        """Get a channel by index.
        
        Args:
            index: Channel number (0-15)
            
        Returns:
            PCAChannel object
            
        Raises:
            IndexError: If index is out of range
        """
        if not 0 <= index <= 15:
            raise IndexError(f"Channel must be 0-15, got {index}")
        return self._channels[index]

    def __len__(self) -> int:
        """Get number of channels.
        
        Returns:
            Number of channels (always 16)
        """
        return 16


class PCA9685:
    """PCA9685 16-channel 12-bit PWM driver.
    
    This implementation uses smbus2 for direct I2C communication,
    replacing the Adafruit CircuitPython library.
    
    The PCA9685 has 16 PWM channels with 12-bit resolution (0-4095).
    Each channel can be independently controlled.
    
    Example:
        >>> from boneio.hardware.i2c.bus import SMBus2I2C
        >>> from boneio.hardware.gpio.expanders import PCA9685
        >>> 
        >>> i2c = SMBus2I2C(bus_num=2)
        >>> pca = PCA9685(i2c=i2c, address=0x40)
        >>> pca.frequency = 1000  # Set PWM frequency to 1000 Hz
        >>> 
        >>> # Control channel 0
        >>> channel = pca.channels[0]
        >>> channel.duty_cycle = 32768  # 50% duty cycle (0-65535 scale)
        >>> channel.duty_cycle = 0      # Turn off
    """

    def __init__(
        self,
        i2c: SMBus2I2C,
        address: int = 0x40,
        reference_clock_speed: int = 25000000,
    ) -> None:
        """Initialize PCA9685.
        
        Args:
            i2c: I2C bus instance (SMBus2I2C)
            address: I2C address of the device (default 0x40)
            reference_clock_speed: Internal oscillator frequency in Hz (default 25 MHz)
        """
        self._i2c = i2c
        self._address = address
        self._reference_clock_speed = reference_clock_speed
        
        # Lock for thread-safe channel operations
        # This prevents race conditions when multiple outputs are switched simultaneously
        self._lock = threading.Lock()
        
        # Timestamp of last I2C operation for rate limiting
        self._last_operation_time = 0.0
        
        # Initialize channels container
        self.channels = PCAChannels(self)
        
        # Reset device
        self._reset()
        
        _LOGGER.debug(
            "Initialized PCA9685 at address 0x%02X with %d MHz clock",
            address,
            reference_clock_speed // 1000000,
        )

    def _reset(self) -> None:
        """Reset the PCA9685 to default state."""
        # Set MODE1 to default (sleep mode, auto-increment enabled)
        self._write_register(MODE1, SLEEP | AI)
        
        # Set MODE2 to default (totem pole outputs)
        self._write_register(MODE2, OUTDRV)
        
        # Wait for oscillator to stabilize
        time.sleep(0.005)
        
        _LOGGER.debug("PCA9685 0x%02X: Reset complete", self._address)

    def _write_register(self, register: int, value: int) -> None:
        """Write a single byte to a register.
        
        Args:
            register: Register address
            value: Byte value to write
        """
        try:
            self._i2c.write_byte_data(self._address, register, value)
            _LOGGER.debug(
                "PCA9685 0x%02X: Wrote 0x%02X to register 0x%02X",
                self._address,
                value,
                register,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to write to PCA9685 at 0x%02X register 0x%02X: %s",
                self._address,
                register,
                e,
            )
            raise

    def _read_register(self, register: int) -> int:
        """Read a single byte from a register.
        
        Args:
            register: Register address
            
        Returns:
            Byte value read from register
        """
        try:
            value = self._i2c.read_byte_data(self._address, register)
            _LOGGER.debug(
                "PCA9685 0x%02X: Read 0x%02X from register 0x%02X",
                self._address,
                value,
                register,
            )
            return value
        except Exception as e:
            _LOGGER.error(
                "Failed to read from PCA9685 at 0x%02X register 0x%02X: %s",
                self._address,
                register,
                e,
            )
            raise

    def _write_channel(self, channel: int, value: int) -> None:
        """Write PWM value to a channel (0-4095).
        
        Thread-safe operation with rate limiting to prevent I2C bus contention.
        
        Args:
            channel: Channel number (0-15)
            value: PWM value (0-4095, 12-bit)
        """
        if not 0 <= channel <= 15:
            raise ValueError(f"Channel must be 0-15, got {channel}")
        
        if not 0 <= value <= 4095:
            raise ValueError(f"PWM value must be 0-4095, got {value}")
        
        with self._lock:
            # Rate limiting: ensure minimum delay between I2C operations
            now = time.monotonic()
            elapsed = now - self._last_operation_time
            if elapsed < I2C_OPERATION_DELAY:
                time.sleep(I2C_OPERATION_DELAY - elapsed)
            
            # Calculate register addresses for this channel
            # Each channel has 4 registers: ON_L, ON_H, OFF_L, OFF_H
            base_reg = LED0_ON_L + (channel * 4)
            
            # For normal PWM:
            # - ON time = 0 (start at beginning of cycle)
            # - OFF time = value (turn off at specified point)
            on_time = 0
            off_time = value
            
            # Special case: full off (value = 0)
            if value == 0:
                # Set bit 12 of OFF time to turn LED fully off
                off_time = 0x1000
            # Special case: full on (value = 4095)
            elif value == 4095:
                # Set bit 12 of ON time to turn LED fully on
                on_time = 0x1000
                off_time = 0
            
            # Write 4 bytes: ON_L, ON_H, OFF_L, OFF_H
            data = [
                on_time & 0xFF,         # ON_L
                (on_time >> 8) & 0xFF,  # ON_H
                off_time & 0xFF,        # OFF_L
                (off_time >> 8) & 0xFF, # OFF_H
            ]
            
            try:
                self._i2c.write_i2c_block_data(self._address, base_reg, data)
                _LOGGER.debug(
                    "PCA9685 0x%02X: Channel %d set to %d (ON=0x%04X, OFF=0x%04X)",
                    self._address,
                    channel,
                    value,
                    on_time,
                    off_time,
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to write channel %d on PCA9685 at 0x%02X: %s",
                    channel,
                    self._address,
                    e,
                )
                raise
            
            self._last_operation_time = time.monotonic()

    def _read_channel(self, channel: int) -> int:
        """Read PWM value from a channel (0-4095).
        
        Args:
            channel: Channel number (0-15)
            
        Returns:
            PWM value (0-4095, 12-bit)
        """
        if not 0 <= channel <= 15:
            raise ValueError(f"Channel must be 0-15, got {channel}")
        
        # Calculate register addresses for this channel
        base_reg = LED0_ON_L + (channel * 4)
        
        try:
            # Read 4 bytes: ON_L, ON_H, OFF_L, OFF_H
            data = self._i2c.read_i2c_block_data(self._address, base_reg, 4)
            
            on_time = data[0] | (data[1] << 8)
            off_time = data[2] | (data[3] << 8)
            
            # Check for special cases
            if on_time & 0x1000:  # Bit 12 set in ON time = fully on
                value = 4095
            elif off_time & 0x1000:  # Bit 12 set in OFF time = fully off
                value = 0
            else:
                # Normal PWM: value is the OFF time
                value = off_time & 0x0FFF
            
            _LOGGER.debug(
                "PCA9685 0x%02X: Channel %d read as %d (ON=0x%04X, OFF=0x%04X)",
                self._address,
                channel,
                value,
                on_time,
                off_time,
            )
            
            return value
        except Exception as e:
            _LOGGER.error(
                "Failed to read channel %d on PCA9685 at 0x%02X: %s",
                channel,
                self._address,
                e,
            )
            raise

    @property
    def frequency(self) -> float:
        """Get the PWM frequency in Hz.
        
        Returns:
            PWM frequency in Hz
        """
        # Read prescale value
        prescale = self._read_register(PRESCALE)
        
        # Calculate frequency: freq = clock / (4096 * (prescale + 1))
        freq = self._reference_clock_speed / (4096 * (prescale + 1))
        
        return freq

    @frequency.setter
    def frequency(self, freq: float) -> None:
        """Set the PWM frequency in Hz.
        
        Valid range is approximately 40 Hz to 1000 Hz.
        
        Args:
            freq: PWM frequency in Hz
            
        Raises:
            ValueError: If frequency is out of range
        """
        if not 40 <= freq <= 1000:
            raise ValueError(f"Frequency must be 40-1000 Hz, got {freq}")
        
        # Calculate prescale value: prescale = (clock / (4096 * freq)) - 1
        prescale = int(self._reference_clock_speed / (4096 * freq) - 1)
        
        if not 0x03 <= prescale <= 0xFF:
            raise ValueError(f"Calculated prescale {prescale} out of range")
        
        # To set prescale, we need to put device to sleep
        old_mode = self._read_register(MODE1)
        
        # Set sleep bit
        self._write_register(MODE1, (old_mode & 0x7F) | SLEEP)
        
        # Write prescale
        self._write_register(PRESCALE, prescale)
        
        # Restore old mode
        self._write_register(MODE1, old_mode)
        
        # Wait for oscillator to stabilize
        time.sleep(0.005)
        
        # Restart if needed
        if old_mode & RESTART:
            self._write_register(MODE1, old_mode | RESTART)
        
        _LOGGER.debug(
            "PCA9685 0x%02X: Set frequency to %.2f Hz (prescale=%d)",
            self._address,
            freq,
            prescale,
        )

    def deinit(self) -> None:
        """Deinitialize the PCA9685.
        
        Turns off all channels and puts device to sleep.
        """
        # Turn off all channels
        for i in range(16):
            self._write_channel(i, 0)
        
        # Put device to sleep
        self._write_register(MODE1, SLEEP)
        
        _LOGGER.debug("PCA9685 0x%02X: Deinitialized", self._address)
