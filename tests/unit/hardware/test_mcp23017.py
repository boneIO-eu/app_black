"""Unit tests for MCP23017 GPIO expander."""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tests.mocks.i2c import MockSMBus2I2C, MockMCP23017Registers
from boneio.hardware.gpio.expanders.mcp23017 import MCP23017, IODIRA, IODIRB, OLATA, OLATB


class TestMCP23017Initialization:
    """Test MCP23017 initialization."""
    
    def test_init_sets_all_pins_as_outputs(self):
        """MCP23017 should configure all pins as outputs on init."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        mock_i2c.add_device(0x20, MockMCP23017Registers.default())
        
        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False)  # type: ignore[arg-type]
        
        # IODIR registers should be 0x00 (all outputs)
        assert mock_i2c.get_register(0x20, IODIRA) == 0x00
        assert mock_i2c.get_register(0x20, IODIRB) == 0x00
    
    def test_init_preserves_relay_states(self):
        """MCP23017 should preserve existing relay states on hot restart (no momentary OFF)."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        
        # Simulate hot restart: IODIR already set to OUTPUT (0x00) by previous session
        registers = MockMCP23017Registers.default()
        registers[IODIRA] = 0x00  # Already outputs (hot restart)
        registers[IODIRB] = 0x00
        registers[OLATA] = 0b00001111  # Pins 0-3 ON
        registers[OLATB] = 0b11110000  # Pins 12-15 ON
        mock_i2c.add_device(0x20, registers)
        
        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False)  # type: ignore[arg-type]
        
        # OLAT registers should be preserved (not cleared to 0x00)
        assert mock_i2c.get_register(0x20, OLATA) == 0b00001111
        assert mock_i2c.get_register(0x20, OLATB) == 0b11110000
        
        # Verify internal state cache matches
        assert mcp.get_pin_value(0) is True
        assert mcp.get_pin_value(3) is True
        assert mcp.get_pin_value(4) is False
        assert mcp.get_pin_value(12) is True
        assert mcp.get_pin_value(15) is True
    
    def test_init_with_different_address(self):
        """MCP23017 should work with different I2C addresses."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        mock_i2c.add_device(0x27, MockMCP23017Registers.default())
        
        mcp = MCP23017(i2c=mock_i2c, address=0x27, reset=False)  # type: ignore[arg-type]
        
        assert mock_i2c.get_register(0x27, IODIRA) == 0x00
    
    def test_init_invalid_address_too_low(self):
        """MCP23017 should reject addresses below 0x20."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        
        with pytest.raises(ValueError, match="MCP23017 address must be 0x20-0x27"):
            MCP23017(i2c=mock_i2c, address=0x1F, reset=False)  # type: ignore[arg-type]
    
    def test_init_invalid_address_too_high(self):
        """MCP23017 should reject addresses above 0x27."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        
        with pytest.raises(ValueError, match="MCP23017 address must be 0x20-0x27"):
            MCP23017(i2c=mock_i2c, address=0x28, reset=False)  # type: ignore[arg-type]


class TestMCP23017PinControl:
    """Test MCP23017 pin control."""
    
    @pytest.fixture
    def mcp(self):
        """Create MCP23017 instance with mock I2C."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        mock_i2c.add_device(0x20, MockMCP23017Registers.default())
        return MCP23017(i2c=mock_i2c, address=0x20, reset=False), mock_i2c  # type: ignore[arg-type]
    
    def test_set_pin_0_high(self, mcp):
        """Setting pin 0 high should set bit 0 in OLATA."""
        mcp_device, mock_i2c = mcp
        
        mcp_device.set_pin_value(0, True)
        
        assert mock_i2c.get_register(0x20, OLATA) & 0x01 == 0x01
    
    def test_set_pin_0_low(self, mcp):
        """Setting pin 0 low should clear bit 0 in OLATA."""
        mcp_device, mock_i2c = mcp
        
        mcp_device.set_pin_value(0, True)
        mcp_device.set_pin_value(0, False)
        
        assert mock_i2c.get_register(0x20, OLATA) & 0x01 == 0x00
    
    def test_set_pin_7_high(self, mcp):
        """Setting pin 7 high should set bit 7 in OLATA."""
        mcp_device, mock_i2c = mcp
        
        mcp_device.set_pin_value(7, True)
        
        assert mock_i2c.get_register(0x20, OLATA) & 0x80 == 0x80
    
    def test_set_pin_8_high(self, mcp):
        """Setting pin 8 high should set bit 0 in OLATB (Port B)."""
        mcp_device, mock_i2c = mcp
        
        mcp_device.set_pin_value(8, True)
        
        assert mock_i2c.get_register(0x20, OLATB) & 0x01 == 0x01
    
    def test_set_pin_15_high(self, mcp):
        """Setting pin 15 high should set bit 7 in OLATB."""
        mcp_device, mock_i2c = mcp
        
        mcp_device.set_pin_value(15, True)
        
        assert mock_i2c.get_register(0x20, OLATB) & 0x80 == 0x80
    
    def test_multiple_pins(self, mcp):
        """Setting multiple pins should work independently."""
        mcp_device, mock_i2c = mcp
        
        mcp_device.set_pin_value(0, True)
        mcp_device.set_pin_value(2, True)
        mcp_device.set_pin_value(4, True)
        
        # Bits 0, 2, 4 should be set = 0b00010101 = 0x15
        assert mock_i2c.get_register(0x20, OLATA) == 0x15
    
    def test_get_pin_value(self, mcp):
        """get_pin_value should return current state."""
        mcp_device, mock_i2c = mcp
        
        mcp_device.set_pin_value(5, True)
        
        assert mcp_device.get_pin_value(5) is True
        assert mcp_device.get_pin_value(4) is False


class TestMCP23017Validation:
    """Test MCP23017 input validation."""
    
    @pytest.fixture
    def mcp(self):
        """Create MCP23017 instance with mock I2C."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        mock_i2c.add_device(0x20, MockMCP23017Registers.default())
        return MCP23017(i2c=mock_i2c, address=0x20, reset=False)  # type: ignore[arg-type]
    
    def test_invalid_pin_negative(self, mcp):
        """Negative pin number should raise ValueError."""
        with pytest.raises(ValueError, match="Pin number must be 0-15"):
            mcp.set_pin_value(-1, True)
    
    def test_invalid_pin_too_high(self, mcp):
        """Pin number > 15 should raise ValueError."""
        with pytest.raises(ValueError, match="Pin number must be 0-15"):
            mcp.set_pin_value(16, True)
    
    def test_configure_pin_as_output(self, mcp):
        """configure_pin_as_output should work without error."""
        mcp.configure_pin_as_output(0, value=True)
        assert mcp.get_pin_value(0) is True


class TestMCP23017Inverted:
    """Test MCP23017 inverted (active-LOW) logic and auto-detection."""

    def test_init_inverted_true_sets_olat_high_on_cold_boot(self):
        """When inverted=True on cold boot (IODIR=0xFF), OLAT registers should be set to 0xFF."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        registers = MockMCP23017Registers.default()  # IODIR=0xFF, OLAT=0x00
        mock_i2c.add_device(0x20, registers)

        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False, inverted=True)  # type: ignore[arg-type]

        assert mcp.inverted is True
        # Hardware OLAT registers should be 0xFF (all physical HIGH -> all relays OFF)
        assert mock_i2c.get_register(0x20, OLATA) == 0xFF
        assert mock_i2c.get_register(0x20, OLATB) == 0xFF

    def test_inverted_set_pin_value_lowers_physical_bit(self):
        """Setting logical ON (True) when inverted=True should write 0 (LOW) to physical OLAT bit."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        registers = MockMCP23017Registers.default()
        mock_i2c.add_device(0x20, registers)

        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False, inverted=True)  # type: ignore[arg-type]

        # Logical ON -> physical LOW -> OLATA bit 0 cleared (0xFF -> 0xFE)
        mcp.set_pin_value(0, True)
        assert mock_i2c.get_register(0x20, OLATA) == 0xFE
        assert mcp.get_pin_value(0) is True

        # Logical OFF -> physical HIGH -> OLATA bit 0 set (0xFE -> 0xFF)
        mcp.set_pin_value(0, False)
        assert mock_i2c.get_register(0x20, OLATA) == 0xFF
        assert mcp.get_pin_value(0) is False

    def test_auto_detect_inverted_when_gpio_is_0xff(self):
        """Cold boot with GPIOA=0xFF, GPIOB=0xFF should auto-detect inverted=True."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        registers = MockMCP23017Registers.default()
        registers[0x12] = 0xFF  # GPIOA = 0xFF (pull-ups present)
        registers[0x13] = 0xFF  # GPIOB = 0xFF
        mock_i2c.add_device(0x20, registers)

        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False)  # type: ignore[arg-type]

        assert mcp.inverted is True

    def test_auto_detect_not_inverted_when_gpio_is_0x00(self):
        """Cold boot with GPIOA=0x00, GPIOB=0x00 should auto-detect inverted=False."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        registers = MockMCP23017Registers.default()
        registers[0x12] = 0x00  # GPIOA = 0x00 (no pull-ups)
        registers[0x13] = 0x00  # GPIOB = 0x00
        mock_i2c.add_device(0x20, registers)

        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False)  # type: ignore[arg-type]

        assert mcp.inverted is False

    def test_inverted_hot_restart_preserves_states(self):
        """Hot restart with inverted=True config should preserve relay states and invert correctly."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        registers = MockMCP23017Registers.default()
        registers[IODIRA] = 0x00  # Already outputs (hot restart)
        registers[IODIRB] = 0x00
        # Pin 0 relay ON = physical LOW (0xFE), pin 1 relay OFF = physical HIGH
        registers[OLATA] = 0xFE  # bit 0 cleared (relay ON), bits 1-7 set (OFF)
        registers[OLATB] = 0xFF  # all HIGH (all OFF)
        mock_i2c.add_device(0x20, registers)

        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False, inverted=True)  # type: ignore[arg-type]

        # Hardware should not change OLAT values
        assert mock_i2c.get_register(0x20, OLATA) == 0xFE
        assert mock_i2c.get_register(0x20, OLATB) == 0xFF

        # Logical values should be inverted: physical LOW (0) → logical ON (True)
        assert mcp.get_pin_value(0) is True   # physical LOW → logical ON
        assert mcp.get_pin_value(1) is False  # physical HIGH → logical OFF
        assert mcp.get_pin_value(8) is False  # physical HIGH → logical OFF


class TestMCP23017ColdBootSafeLevel:
    """Cold boot must latch the OFF level for the board's polarity.

    On cold boot the pins are still inputs, so nothing is driven and there is no
    relay state worth preserving. The latch has to be primed with the level that
    means OFF for this board *before* IODIR turns the pins into outputs.
    """

    def test_active_high_cold_boot_forces_latches_low(self):
        """active-HIGH: OFF is LOW, so stale latch content must not be preserved."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        registers = MockMCP23017Registers.default()  # cold boot: IODIR = 0xFF
        # A glitched expander can come back with non-zero latches. Preserving
        # them on an active-HIGH board would energise every relay the moment
        # IODIR enables the drivers.
        registers[OLATA] = 0xFF
        registers[OLATB] = 0xFF
        mock_i2c.add_device(0x20, registers)

        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False, inverted=False)  # type: ignore[arg-type]

        assert mcp.inverted is False
        assert mock_i2c.get_register(0x20, OLATA) == 0x00
        assert mock_i2c.get_register(0x20, OLATB) == 0x00
        assert mcp.get_pin_value(0) is False
        assert mcp.get_pin_value(15) is False

    def test_active_low_cold_boot_forces_latches_high(self):
        """active-LOW: OFF is HIGH."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        registers = MockMCP23017Registers.default()
        registers[OLATA] = 0x00
        registers[OLATB] = 0x00
        mock_i2c.add_device(0x20, registers)

        mcp = MCP23017(i2c=mock_i2c, address=0x20, reset=False, inverted=True)  # type: ignore[arg-type]

        assert mock_i2c.get_register(0x20, OLATA) == 0xFF
        assert mock_i2c.get_register(0x20, OLATB) == 0xFF
        # 0xFF is the physical OFF level for an active-LOW board.
        assert mcp.get_pin_value(0) is False


class TestMCP23017HealthCheck:
    """The watchdog that catches an expander which quietly stopped driving."""

    @staticmethod
    def _make(address: int = 0x20, inverted: bool = False):
        mock_i2c = MockSMBus2I2C(bus_number=2)
        registers = MockMCP23017Registers.default()
        registers[IODIRA] = 0x00  # warm start: already configured
        registers[IODIRB] = 0x00
        mock_i2c.add_device(address, registers)
        mcp = MCP23017(i2c=mock_i2c, address=address, reset=False, inverted=inverted)  # type: ignore[arg-type]
        return mock_i2c, mcp

    def test_healthy_expander_needs_no_repair(self):
        mock_i2c, mcp = self._make()
        assert mcp.health_check() is False

    def test_iodir_reset_to_inputs_is_detected_and_repaired(self):
        """The actual field failure: chip reset back to all-inputs.

        Writes to OLAT keep succeeding and read back correctly, so nothing in
        the write path can notice. Only IODIR gives it away.
        """
        mock_i2c, mcp = self._make()
        mcp.set_pin_value(2, True)

        # Simulate the expander losing its configuration (brown-out / glitch).
        mock_i2c.set_register(0x20, IODIRA, 0xFF)
        mock_i2c.set_register(0x20, IODIRB, 0xFF)

        # A write still "succeeds" — this is why the failure is silent.
        mcp.set_pin_value(3, True)
        assert mock_i2c.get_register(0x20, IODIRA) == 0xFF

        assert mcp.health_check() is True
        assert mock_i2c.get_register(0x20, IODIRA) == 0x00
        assert mock_i2c.get_register(0x20, IODIRB) == 0x00

    def test_repair_restores_commanded_relay_states(self):
        """After repair the latches must hold what software last commanded."""
        mock_i2c, mcp = self._make()
        mcp.set_pin_value(0, True)
        mcp.set_pin_value(5, True)
        mcp.set_pin_value(9, True)
        expected_a = mock_i2c.get_register(0x20, OLATA)
        expected_b = mock_i2c.get_register(0x20, OLATB)

        # Full power-on reset: IODIR back to inputs AND latches cleared.
        mock_i2c.set_register(0x20, IODIRA, 0xFF)
        mock_i2c.set_register(0x20, IODIRB, 0xFF)
        mock_i2c.set_register(0x20, OLATA, 0x00)
        mock_i2c.set_register(0x20, OLATB, 0x00)

        assert mcp.health_check() is True
        assert mock_i2c.get_register(0x20, OLATA) == expected_a
        assert mock_i2c.get_register(0x20, OLATB) == expected_b
        assert mcp.get_pin_value(0) is True
        assert mcp.get_pin_value(5) is True
        assert mcp.get_pin_value(9) is True

    def test_repair_writes_latches_before_enabling_outputs(self):
        """Ordering matters: latch first, then IODIR.

        Enabling the drivers before restoring the latch would drive the relays
        to the power-on value first and glitch them.
        """
        mock_i2c, mcp = self._make()
        mcp.set_pin_value(1, True)
        mock_i2c.set_register(0x20, IODIRA, 0xFF)
        mock_i2c.set_register(0x20, IODIRB, 0xFF)
        mock_i2c.set_register(0x20, OLATA, 0x00)

        writes: list[tuple[int, int]] = []
        original = mock_i2c.write_byte_data

        def recording_write(address: int, register: int, value: int) -> None:
            writes.append((register, value))
            original(address, register, value)

        mock_i2c.write_byte_data = recording_write  # type: ignore[method-assign]
        assert mcp.health_check() is True

        assert OLATA in [reg for reg, _ in writes], writes
        assert writes.index((OLATA, mcp._port_a_state)) < writes.index((IODIRA, 0x00))
        assert writes.index((OLATB, mcp._port_b_state)) < writes.index((IODIRB, 0x00))

    def test_bank1_is_detected_and_forced_back_to_bank0(self):
        """A chip knocked into BANK=1 addresses a different register map.

        Detection cannot rely on IOCON at 0x0A — with BANK=1 that address is
        OLATA. Register 0x05 is the discriminator: IOCON (bit 7 set) in BANK=1,
        GPINTENB (kept at 0) in BANK=0.
        """
        mock_i2c, mcp = self._make()
        mock_i2c.set_register(0x20, 0x05, 0xA0)  # IOCON with BANK=1 set

        assert mcp.health_check() is True
        # 0x05 zeroed puts the map back to BANK=0, then IOCON gets its value.
        assert mock_i2c.get_register(0x20, 0x05) == 0x00
        assert mock_i2c.get_register(0x20, 0x0A) == 0x20
        assert mock_i2c.get_register(0x20, IODIRA) == 0x00
        assert mock_i2c.get_register(0x20, IODIRB) == 0x00

    def test_health_check_never_raises_on_i2c_failure(self):
        """The watchdog must survive a failing bus, not kill its task."""
        mock_i2c, mcp = self._make()

        def boom(address: int, register: int) -> int:
            raise OSError("bus error")

        mock_i2c.read_byte_data = boom  # type: ignore[method-assign]
        assert mcp.health_check() is False
