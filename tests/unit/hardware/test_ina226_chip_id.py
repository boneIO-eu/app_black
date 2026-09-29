"""INA226 driver refuses a chip that is not an INA226.

An INA219 answers at the same address. Configured as an INA226 it read
40 V on a 24 V supply: our config word put it in its 16 V range and the
16 V it saturated at was scaled by the INA226 LSB.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from boneio.exceptions import I2CError
from boneio.hardware.i2c.ina226_driver import INA226_I2C


def _smbus_returning(manufacturer_id_on_wire: int) -> MagicMock:
    """SMBus mock whose register 0xFE reads the given little-endian word."""
    bus = MagicMock()
    bus.read_word_data.return_value = manufacturer_id_on_wire
    return bus


def test_ina226_is_configured():
    bus = _smbus_returning(0x4954)  # 0x5449 "TI" byte-swapped by SMBus
    with patch("boneio.hardware.i2c.ina226_driver.smbus2.SMBus", return_value=bus):
        INA226_I2C(address=0x40, _bus=2)

    written_registers = [c.args[1] for c in bus.write_word_data.call_args_list]
    assert written_registers == [INA226_I2C.REG_CONFIG, INA226_I2C.REG_CALIBRATION]
    bus.close.assert_not_called()


def test_ina219_is_refused_before_any_write():
    # What an INA219 returned for 0xFE on a board in the field.
    bus = _smbus_returning(0x0020)
    with patch("boneio.hardware.i2c.ina226_driver.smbus2.SMBus", return_value=bus):
        with pytest.raises(I2CError, match=r"not an INA226.*0x2000.*ina219:"):
            INA226_I2C(address=0x40, _bus=2)

    bus.write_word_data.assert_not_called()
    bus.close.assert_called_once()
