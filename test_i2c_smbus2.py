#!/usr/bin/env python3
"""Test script for smbus2 I2C wrapper on BeagleBone Black with Python 3.13.

This script tests the SMBus2I2CWrapper to ensure it works correctly
with Adafruit CircuitPython libraries.
"""

import sys
import logging

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
_LOGGER = logging.getLogger(__name__)


def test_i2c_wrapper():
    """Test basic I2C wrapper functionality."""
    _LOGGER.info("Testing SMBus2I2CWrapper...")
    
    try:
        from boneio.helper.i2c_wrapper import SMBus2I2CWrapper
        
        # Initialize I2C bus
        i2c = SMBus2I2CWrapper(bus_number=2)
        _LOGGER.info("✅ I2C wrapper initialized successfully")
        
        # Scan for devices
        _LOGGER.info("Scanning I2C bus for devices...")
        devices = i2c.scan()
        
        if devices:
            _LOGGER.info(f"✅ Found {len(devices)} I2C device(s):")
            for addr in devices:
                _LOGGER.info(f"   - 0x{addr:02X}")
        else:
            _LOGGER.warning("⚠️  No I2C devices found")
        
        return True
        
    except Exception as e:
        _LOGGER.error(f"❌ I2C wrapper test failed: {e}")
        return False


def test_mcp23017():
    """Test MCP23017 with smbus2 wrapper."""
    _LOGGER.info("\nTesting MCP23017...")
    
    try:
        from adafruit_mcp230xx.mcp23017 import MCP23017
        from boneio.helper.i2c_wrapper import SMBus2I2CWrapper
        
        i2c = SMBus2I2CWrapper(bus_number=2)
        
        # Try common MCP23017 addresses
        addresses = [0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27]
        
        for addr in addresses:
            try:
                mcp = MCP23017(i2c=i2c, address=addr, reset=False)
                _LOGGER.info(f"✅ MCP23017 found at address 0x{addr:02X}")
                
                # Try to get a pin (basic test)
                pin = mcp.get_pin(0)
                _LOGGER.info(f"   - Successfully accessed pin 0")
                return True
                
            except Exception as e:
                _LOGGER.debug(f"   No MCP23017 at 0x{addr:02X}: {e}")
                continue
        
        _LOGGER.warning("⚠️  No MCP23017 found at common addresses")
        return False
        
    except ImportError as e:
        _LOGGER.error(f"❌ MCP23017 library not available: {e}")
        return False
    except Exception as e:
        _LOGGER.error(f"❌ MCP23017 test failed: {e}")
        return False


def test_pca9685():
    """Test PCA9685 with smbus2 wrapper."""
    _LOGGER.info("\nTesting PCA9685...")
    
    try:
        from adafruit_pca9685 import PCA9685
        from boneio.helper.i2c_wrapper import SMBus2I2CWrapper
        
        i2c = SMBus2I2CWrapper(bus_number=2)
        
        # Try common PCA9685 addresses
        addresses = [0x40, 0x41, 0x42, 0x43]
        
        for addr in addresses:
            try:
                pca = PCA9685(i2c, address=addr)
                _LOGGER.info(f"✅ PCA9685 found at address 0x{addr:02X}")
                
                # Set frequency (basic test)
                pca.frequency = 50
                _LOGGER.info(f"   - Successfully set frequency")
                return True
                
            except Exception as e:
                _LOGGER.debug(f"   No PCA9685 at 0x{addr:02X}: {e}")
                continue
        
        _LOGGER.warning("⚠️  No PCA9685 found at common addresses")
        return False
        
    except ImportError as e:
        _LOGGER.error(f"❌ PCA9685 library not available: {e}")
        return False
    except Exception as e:
        _LOGGER.error(f"❌ PCA9685 test failed: {e}")
        return False


def test_pcf8575():
    """Test PCF8575 with smbus2 wrapper."""
    _LOGGER.info("\nTesting PCF8575...")
    
    try:
        from boneio.helper.pcf8575 import PCF8575
        from boneio.helper.i2c_wrapper import SMBus2I2CWrapper
        
        i2c = SMBus2I2CWrapper(bus_number=2)
        
        # Try common PCF8575 addresses
        addresses = [0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27]
        
        for addr in addresses:
            try:
                pcf = PCF8575(i2c=i2c, address=addr, reset=False)
                _LOGGER.info(f"✅ PCF8575 found at address 0x{addr:02X}")
                return True
                
            except Exception as e:
                _LOGGER.debug(f"   No PCF8575 at 0x{addr:02X}: {e}")
                continue
        
        _LOGGER.warning("⚠️  No PCF8575 found at common addresses")
        return False
        
    except ImportError as e:
        _LOGGER.error(f"❌ PCF8575 library not available: {e}")
        return False
    except Exception as e:
        _LOGGER.error(f"❌ PCF8575 test failed: {e}")
        return False


def main():
    """Run all tests."""
    _LOGGER.info("=" * 60)
    _LOGGER.info("BoneIO I2C smbus2 Wrapper Test Suite")
    _LOGGER.info(f"Python version: {sys.version}")
    _LOGGER.info("=" * 60)
    
    results = {
        "I2C Wrapper": test_i2c_wrapper(),
        "MCP23017": test_mcp23017(),
        "PCA9685": test_pca9685(),
        "PCF8575": test_pcf8575(),
    }
    
    _LOGGER.info("\n" + "=" * 60)
    _LOGGER.info("Test Results:")
    _LOGGER.info("=" * 60)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        _LOGGER.info(f"{test_name:20s}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        _LOGGER.info("\n🎉 All tests passed!")
        return 0
    else:
        _LOGGER.warning("\n⚠️  Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
