# Migration Notes: PCF8575 to smbus2

**Date:** 2025-10-22  
**Component:** PCF8575 I2C GPIO Expander  
**Migration:** Adafruit CircuitPython → Native smbus2 implementation

---

## Overview

Migrated PCF8575 16-bit I/O expander from Adafruit CircuitPython library to native smbus2 implementation for Python 3.13+ compatibility.

## Changes Made

### 1. New Implementation

**File:** `boneio/hardware/gpio/expanders/pcf8575.py` (270 lines)

**Features:**
- Native smbus2 I2C communication
- 16-bit quasi-bidirectional I/O (pins 0-15)
- Output and input modes supported
- State tracking for all pins
- API compatible with Adafruit implementation

**Protocol:**
- Write: 2 bytes (Port 0: pins 0-7, Port 1: pins 8-15)
- Read: 2 bytes from device
- Output: Bit=0 (LOW), Bit=1 (HIGH)
- Input: Bit=1 (enables pull-up), then read

**Key Classes:**
```python
class PCF8575:
    """Main PCF8575 driver"""
    def __init__(self, i2c: SMBus2I2C, address: int, reset: bool = False)
    def get_pin(self, pin: int) -> PCF8575DigitalInOut
    
class PCF8575DigitalInOut:
    """Digital I/O pin wrapper"""
    def switch_to_output(self, value: bool = False)
    def switch_to_input(self)
    @property value -> bool
```

### 2. Updated Imports

**Files Modified:**
- `boneio/core/config/loader.py` - Import from `hardware.gpio.expanders`
- `boneio/relay/pcf.py` - Import PCF8575 and PCF8575DigitalInOut
- `boneio/hardware/gpio/expanders/__init__.py` - Export PCF8575

**Before:**
```python
from boneio.helper.pcf8575 import PCF8575
from adafruit_pcf8575 import DigitalInOut
```

**After:**
```python
from boneio.hardware.gpio.expanders import PCF8575
from boneio.hardware.gpio.expanders.pcf8575 import PCF8575DigitalInOut
```

### 3. Backward Compatibility

**File:** `boneio/helper/pcf8575.py`

Now acts as a re-export wrapper:
```python
from boneio.hardware.gpio.expanders import PCF8575
__all__ = ["PCF8575"]
```

Old code continues to work:
```python
from boneio.helper.pcf8575 import PCF8575  # Still works
```

### 4. Dependency Removal

**Removed from `pyproject.toml`:**
```toml
"adafruit-circuitpython-pcf8575==1.0.11"
```

**Kept:**
```toml
"smbus2==0.4.3"  # Core I2C communication
```

---

## Technical Details

### PCF8575 Register Map

The PCF8575 doesn't have traditional registers. It uses a simple 2-byte protocol:

**Write Operation:**
```
Byte 0: Port 0 state (pins 0-7)
Byte 1: Port 1 state (pins 8-15)
```

**Read Operation:**
```
Read 2 bytes:
  Byte 0: Port 0 state (pins 0-7)
  Byte 1: Port 1 state (pins 8-15)
```

### Pin Mapping

```
Pin 0-7:  Port 0 (P00-P07)
Pin 8-15: Port 1 (P10-P17)
```

### State Management

The driver maintains internal state (`_state: int`) as a 16-bit value:
- Bit=1: HIGH (output) or input with pull-up enabled
- Bit=0: LOW (output)

This avoids unnecessary I2C reads for output operations.

### I2C Communication

**Write State:**
```python
byte0 = self._state & 0xFF          # Port 0
byte1 = (self._state >> 8) & 0xFF   # Port 1
self._i2c.write_i2c_block_data(self._address, byte0, [byte1])
```

**Read State:**
```python
data = self._i2c.read_i2c_block_data(self._address, 0, 2)
state = data[0] | (data[1] << 8)
```

---

## Usage Example

```python
from boneio.hardware.i2c.bus import SMBus2I2C
from boneio.hardware.gpio.expanders import PCF8575

# Initialize I2C bus
i2c = SMBus2I2C(bus_num=2)

# Initialize PCF8575
pcf = PCF8575(i2c=i2c, address=0x20, reset=False)

# Get pin and configure as output
pin = pcf.get_pin(0)
pin.switch_to_output(value=True)

# Control pin
pin.value = False  # Turn OFF
pin.value = True   # Turn ON

# Configure as input (enables pull-up)
pin.switch_to_input()
state = pin.value  # Read input state
```

---

## Compatibility

### API Compatibility

✅ **100% compatible** with Adafruit API:
- `PCF8575(i2c, address, reset)`
- `get_pin(pin_number)`
- `pin.switch_to_output(value)`
- `pin.switch_to_input()`
- `pin.value` (get/set)

### Behavioral Differences

1. **No actual reset:** The `reset` parameter is accepted but ignored (for API compatibility)
2. **State tracking:** Uses internal state instead of reading from device for outputs
3. **Logging:** Added debug logging for I2C operations

---

## Testing

### Syntax Check
```bash
python3 -m py_compile boneio/hardware/gpio/expanders/pcf8575.py
# ✓ Success
```

### Import Test
```python
from boneio.hardware.gpio.expanders import PCF8575
# ✓ Success (requires smbus2 installed)
```

### Backward Compatibility Test
```python
from boneio.helper.pcf8575 import PCF8575
# ✓ Success
```

---

## Migration Impact

### Files Changed: 5
1. `boneio/hardware/gpio/expanders/pcf8575.py` - **NEW** (270 lines)
2. `boneio/hardware/gpio/expanders/__init__.py` - Updated exports
3. `boneio/core/config/loader.py` - Updated import
4. `boneio/relay/pcf.py` - Updated imports and type annotations
5. `boneio/helper/pcf8575.py` - Converted to re-export wrapper

### Dependencies Removed: 1
- `adafruit-circuitpython-pcf8575==1.0.11`

### Code Using PCF8575
- `boneio/relay/pcf.py` - PCFRelay class (relay control)
- `boneio/core/config/loader.py` - Expander initialization

---

## Next Steps

Continue with Etap 2 refactoring:

1. ✅ **MCP23017** - Completed
2. ✅ **PCF8575** - Completed
3. ⏳ **PCA9685** - PWM driver (next)
4. ⏳ Remove remaining Adafruit dependencies

---

## Notes

- PCF8575 is primarily used for relay control in BoneIO
- The quasi-bidirectional I/O feature allows pins to be used as inputs or outputs
- For BoneIO use case (relay control), output-only mode is sufficient
- Input mode is supported for completeness and future use

---

## References

- PCF8575 Datasheet: 16-bit I2C I/O expander
- smbus2 Documentation: https://smbus2.readthedocs.io/
- Previous migration: MCP23017 (see MIGRATION_NOTES_MCP23017.md)
