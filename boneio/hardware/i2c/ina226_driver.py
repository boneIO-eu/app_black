"""Low-level INA226 I2C driver using smbus2.

This module provides a low-level driver for the INA226 current/voltage/power
monitoring IC (Texas Instruments). The INA226 is used on boneIO Black v1.0 boards,
replacing the INA219 used on v0.8.

Key differences from INA219:
- Bus voltage: 1.25 mV/bit, no bit shift (INA219: 4 mV/bit with 3-bit shift)
- Shunt voltage: 2.5 µV/bit (INA219: 10 µV/bit)
- Power LSB: 25 × Current_LSB (INA219: 20 × Current_LSB)
- Manufacturer/Die ID registers (0xFE/0xFF) for auto-detection
- Bus voltage range: 0–36V (INA219: 0–26V)

Reference: https://www.ti.com/lit/ds/symlink/ina226.pdf
"""

from __future__ import annotations

import logging

import smbus2

_LOGGER = logging.getLogger(__name__)

# INA226 Manufacturer ID (register 0xFE) — always 0x5449 ("TI")
INA226_MANUFACTURER_ID = 0x5449

# INA226 Die ID (register 0xFF) — always 0x2260
INA226_DIE_ID = 0x2260


class INA226_I2C:
    """Low-level INA226 I2C driver.

    This class provides direct register access to the INA226 power monitor IC.
    It handles configuration, calibration, and reading of voltage, current, and power.

    Features:
    - Bus voltage measurement (0–36V, 1.25 mV resolution)
    - Shunt voltage measurement (±81.92 mV, 2.5 µV resolution)
    - Current measurement (calibrated via shunt resistor)
    - Power calculation (internal, 25 × Current_LSB)
    - Configurable averaging and conversion time
    - Manufacturer/Die ID registers for chip identification

    Args:
        address: I2C address (default: 0x40)
        _bus: I2C bus number (default: 2)
        r_shunt: Shunt resistor value in Ohms (default: 0.05 for boneIO v1.0)
        max_current: Maximum expected current in Amps (default: 1.5)

    Example:
        >>> ina = INA226_I2C(address=0x40, _bus=2, r_shunt=0.05)
        >>> voltage = ina.voltage  # Bus voltage in V
        >>> current = ina.current  # Current in A
        >>> power = ina.power      # Power in W
    """

    # Register addresses
    REG_CONFIG = 0x00
    REG_SHUNT_VOLTAGE = 0x01
    REG_BUS_VOLTAGE = 0x02
    REG_POWER = 0x03
    REG_CURRENT = 0x04
    REG_CALIBRATION = 0x05
    REG_MASK_ENABLE = 0x06
    REG_ALERT_LIMIT = 0x07
    REG_MANUFACTURER_ID = 0xFE
    REG_DIE_ID = 0xFF

    # Fixed LSB values
    BUS_VOLTAGE_LSB = 0.00125  # 1.25 mV per bit
    SHUNT_VOLTAGE_LSB = 0.0000025  # 2.5 µV per bit

    # Config register: averaging modes
    AVG_1 = 0x0000
    AVG_4 = 0x0200
    AVG_16 = 0x0400
    AVG_64 = 0x0600
    AVG_128 = 0x0800
    AVG_256 = 0x0A00
    AVG_512 = 0x0C00
    AVG_1024 = 0x0E00

    # Config register: conversion time (bus and shunt)
    CT_140US = 0x0000
    CT_204US = 0x0008
    CT_332US = 0x0010
    CT_588US = 0x0018
    CT_1100US = 0x0020  # default
    CT_2116US = 0x0028
    CT_4156US = 0x0030
    CT_8244US = 0x0038

    # Operating mode
    MODE_POWER_DOWN = 0x0000
    MODE_SHUNT_TRIGGERED = 0x0001
    MODE_BUS_TRIGGERED = 0x0002
    MODE_SHUNT_BUS_TRIGGERED = 0x0003
    MODE_SHUNT_CONTINUOUS = 0x0005
    MODE_BUS_CONTINUOUS = 0x0006
    MODE_SHUNT_BUS_CONTINUOUS = 0x0007  # default

    def __init__(
        self,
        address: int = 0x40,
        _bus: int = 2,
        r_shunt: float = 0.05,
        max_current: float = 1.5,
    ) -> None:
        """Initialize INA226 driver.

        Calculates Current_LSB and calibration register value based on
        the shunt resistor and maximum expected current.

        Args:
            address: I2C address (default: 0x40)
            _bus: I2C bus number (default: 2)
            r_shunt: Shunt resistor in Ohms (default: 0.05 for boneIO v1.0)
            max_current: Maximum expected current in A (default: 1.5)
        """
        self._address = address
        self.bus = smbus2.SMBus(_bus)
        self._r_shunt = r_shunt

        # Calculate Current_LSB (A/bit)
        # Minimum: max_current / 2^15
        self._current_lsb = max_current / 32768

        # Calculate calibration register
        # CAL = trunc(0.00512 / (Current_LSB × R_SHUNT))
        self._cal = int(0.00512 / (self._current_lsb * r_shunt))

        # Power LSB = 25 × Current_LSB (fixed by INA226 hardware)
        self._power_lsb = 25 * self._current_lsb

        _LOGGER.debug(
            "INA226 at 0x%02X: R_SHUNT=%.3fΩ, Current_LSB=%.2fµA, "
            "CAL=%d, Power_LSB=%.4fmW",
            address,
            r_shunt,
            self._current_lsb * 1e6,
            self._cal,
            self._power_lsb * 1e3,
        )

        # Configure: 16× averaging, 1.1ms conversion, continuous shunt+bus
        config = self.AVG_16 | self.CT_1100US | (self.CT_1100US >> 3) | self.MODE_SHUNT_BUS_CONTINUOUS
        self.write_word(self.REG_CONFIG, config)

        # Write calibration register
        self.write_word(self.REG_CALIBRATION, self._cal)

    @staticmethod
    def detect(address: int = 0x40, bus_num: int = 2) -> bool:
        """Check if an INA226 is present at the given I2C address.

        Reads the Manufacturer ID register (0xFE) and checks for the
        TI identifier (0x5449). INA219 does not have this register.

        Args:
            address: I2C address to probe.
            bus_num: I2C bus number.

        Returns:
            True if INA226 is detected, False otherwise.
        """
        try:
            bus = smbus2.SMBus(bus_num)
            try:
                raw = bus.read_word_data(address, 0xFE)
                # Swap bytes (big-endian)
                swapped = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
                return swapped == INA226_MANUFACTURER_ID
            finally:
                bus.close()
        except OSError:
            return False

    @property
    def voltage(self) -> float:
        """Get bus voltage in volts.

        INA226 bus voltage register: raw × 1.25 mV (no bit shift).

        Returns:
            Bus voltage in V (0–36V range).
        """
        raw = self.read_word(self.REG_BUS_VOLTAGE)
        return round(raw * self.BUS_VOLTAGE_LSB, 2)

    @property
    def current(self) -> float:
        """Get current in amperes.

        Re-writes calibration before reading to guard against
        register reset from power glitches.

        Returns:
            Current in A (signed).
        """
        self.write_word(self.REG_CALIBRATION, self._cal)
        raw = self.read_word(self.REG_CURRENT)
        # Handle signed 16-bit (two's complement)
        if raw > 32767:
            raw = raw - 65536
        return round(raw * self._current_lsb, 3)

    @property
    def power(self) -> float:
        """Get power in watts.

        INA226 computes power internally: Power_reg × Power_LSB.
        Power_LSB = 25 × Current_LSB.

        Returns:
            Power in W.
        """
        raw = self.read_word(self.REG_POWER)
        return round(raw * self._power_lsb, 2)

    def get_bus_voltage(self, mV: bool = False) -> float:
        """Read bus voltage.

        Args:
            mV: If True, return in millivolts; if False, return in volts.

        Returns:
            Bus voltage in V or mV.
        """
        raw = self.read_word(self.REG_BUS_VOLTAGE)
        voltage_v = raw * self.BUS_VOLTAGE_LSB
        return round(voltage_v * (1000.0 if mV else 1.0), 2)

    def get_shunt_voltage(self, mV: bool = False) -> float:
        """Read shunt voltage.

        Args:
            mV: If True, return in millivolts; if False, return raw µV.

        Returns:
            Shunt voltage.
        """
        raw = self.read_word(self.REG_SHUNT_VOLTAGE)
        # Handle signed 16-bit
        if raw > 32767:
            raw = raw - 65536
        voltage_v = raw * self.SHUNT_VOLTAGE_LSB
        return round(voltage_v * (1000.0 if mV else 1.0), 4)

    def get_current(self, mA: bool = True) -> float:
        """Read current.

        Args:
            mA: If True, return in milliamps; if False, return in amps.

        Returns:
            Current in A or mA.
        """
        self.write_word(self.REG_CALIBRATION, self._cal)
        raw = self.read_word(self.REG_CURRENT)
        if raw > 32767:
            raw = raw - 65536
        current_a = raw * self._current_lsb
        return round(current_a * (1000.0 if mA else 1.0), 3)

    def get_power(self, mW: bool = True) -> float:
        """Read power.

        Uses the INA226's internal power register which is more accurate
        than computing V×I from separate reads.

        Args:
            mW: If True, return in milliwatts; if False, return in watts.

        Returns:
            Power in W or mW.
        """
        raw = self.read_word(self.REG_POWER)
        power_w = raw * self._power_lsb
        return round(power_w * (1000.0 if mW else 1.0), 2)

    def read_word(self, register: int) -> int:
        """Read 16-bit word from register.

        Args:
            register: Register address.

        Returns:
            16-bit unsigned value.
        """
        raw = self.bus.read_word_data(self._address, register)
        # Swap bytes (SMBus little-endian → INA226 big-endian)
        high_byte = raw & 0xFF
        low_byte = (raw & 0xFF00) >> 8
        return (high_byte << 8) + low_byte

    def write_word(self, register: int, data: int) -> None:
        """Write 16-bit word to register.

        Args:
            register: Register address.
            data: 16-bit value to write.
        """
        # Swap bytes (INA226 big-endian → SMBus little-endian)
        high_byte = data & 0xFF
        low_byte = (data & 0xFF00) >> 8
        swapped = (high_byte << 8) + low_byte
        self.bus.write_word_data(self._address, register, swapped)
