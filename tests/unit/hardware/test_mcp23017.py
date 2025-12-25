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
        """MCP23017 should preserve existing relay states on init (no momentary OFF)."""
        mock_i2c = MockSMBus2I2C(bus_number=2)
        
        # Set up device with some relays already ON (simulating hardware state before restart)
        registers = MockMCP23017Registers.default()
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
