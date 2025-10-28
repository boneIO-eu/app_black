## Migration Notes: OneWire to smbus2

**Date:** 2025-10-22  
**Component:** OneWire (DS2482 I2C to 1-Wire bridge)  
**Migration:** Adafruit CircuitPython → Native smbus2 implementation

---

## Overview

Migrated OneWire implementation (DS2482 bridge and 1-Wire bus) from Adafruit CircuitPython libraries to native smbus2 implementation for Python 3.13+ compatibility.

## Changes Made

### 1. New Implementation

**Files Created:**
- `boneio/hardware/onewire/__init__.py` - Package exports
- `boneio/hardware/onewire/ds2482.py` (450 lines) - DS2482 I2C to 1-Wire bridge
- `boneio/hardware/onewire/bus.py` (370 lines) - OneWire bus protocol

**Features:**
- Native smbus2 I2C communication
- DS2482 I2C to 1-Wire bridge driver
- Complete 1-Wire bus protocol implementation
- Device search algorithm (ROM search)
- API compatible with previous implementation

### 2. DS2482 Driver

**File:** `boneio/hardware/onewire/ds2482.py`

**Key Features:**
- I2C to 1-Wire bridge communication
- Device reset and configuration
- 1-Wire bus reset with presence detection
- Single bit read/write operations
- Byte read/write operations
- Strong pullup support
- Status and config register access

**Registers:**
- STATUS (0xF0): Device status
- DATA (0xE1): Data register
- CONFIG (0xC3): Configuration register

**Commands:**
- DEVICE_RESET (0xF0): Reset DS2482
- 1W_RESET (0xB4): Reset 1-Wire bus
- 1W_SINGLE_BIT (0x87): Single bit operation
- 1W_WRITE_BYTE (0xA5): Write byte to 1-Wire
- 1W_READ_BYTE (0x96): Read byte from 1-Wire

**Key Class:**
```python
class DS2482:
    def __init__(self, i2c: SMBus2I2C, address: int = 0x18, active_pullup: bool = False)
    def device_reset(self) -> None
    @property device_status -> int
    @property device_config -> int
    @device_config.setter device_config(config: int)
    def reset(self) -> bool  # 1-Wire bus reset
    def single_bit(self, bit: int = 1, strong_pullup: bool = False, busy: float | None = None) -> bool
    def write_byte(self, data: int, strong_pullup: bool = False, busy: float | None = None) -> None
    def read_byte(self) -> int
    def wait_ready(self) -> int
```

### 3. OneWire Bus Implementation

**File:** `boneio/hardware/onewire/bus.py`

**Key Features:**
- Low-level OneWire protocol (read/write bits)
- High-level bus operations (read/write bytes)
- 1-Wire search algorithm (ROM search)
- Device address management
- Device selection (Match ROM, Skip ROM)

**Key Classes:**
```python
class OneWireAddress:
    """Represents a 64-bit 1-Wire device address"""
    @property int_address -> int
    @property hex_id -> str
    @property hw_id -> str

class OneWire:
    """Low-level OneWire protocol"""
    def __init__(self, ds2482: DS2482)
    def reset(self) -> bool
    def read_bit(self) -> bool
    def write_bit(self, value: bool) -> None

class OneWireBus:
    """High-level OneWire bus with device search"""
    def __init__(self, ds2482: DS2482)
    def scan(self) -> list[OneWireAddress]
    def reset(self) -> bool
    def read_byte(self) -> int
    def write_byte(self, byte: int) -> None
    def select(self, address: OneWireAddress) -> None
    def skip_rom(self) -> None
```

### 4. 1-Wire Search Algorithm

The implementation includes the standard 1-Wire search algorithm (ROM search) to discover all devices on the bus:

**Algorithm Steps:**
1. Reset bus and send Search ROM command (0xF0)
2. For each of 64 bits in ROM address:
   - Read two bits: id_bit and cmp_id_bit
   - If both 0: discrepancy (multiple devices)
   - If both 1: no devices
   - Otherwise: all devices have same bit
3. Track last discrepancy position
4. Repeat until all devices found

**Maximum Devices:** 20 (configurable via `_MAX_DEVICES`)

### 5. Updated Imports

**Files Modified:**
- `boneio/hardware/onewire/__init__.py` - New package exports
- `boneio/core/config/loader.py` - Import from `hardware.onewire`
- `boneio/helper/onewire/__init__.py` - Backward compatibility wrapper

**Before:**
```python
from boneio.helper.onewire import DS2482, OneWireBus, OneWireAddress
```

**After:**
```python
from boneio.hardware.onewire import DS2482, OneWireBus, OneWireAddress
```

### 6. Removed Files

**Deleted from `boneio/helper/onewire/`:**
- `ds2482.py` - Replaced by `hardware/onewire/ds2482.py`
- `onewire.py` - Replaced by `hardware/onewire/bus.py`

**Kept:**
- `W1ThermSensor.py` - Custom W1ThermSensor wrapper (no Adafruit deps)
- `__init__.py` - Backward compatibility wrapper

### 7. Dependency Removal

**Removed dependencies:**
```toml
# These were transitive dependencies, not directly in pyproject.toml
# but pulled in by adafruit-circuitpython-* packages
adafruit-circuitpython-busdevice
adafruit-circuitpython-onewire
```

**Kept:**
```toml
"smbus2==0.4.3"  # Core I2C communication
"w1thermsensor[async]==2.3.0"  # W1 temperature sensor support
```

---

## Technical Details

### DS2482 I2C to 1-Wire Bridge

**Purpose:** Converts I2C commands to 1-Wire protocol

**I2C Address:** 0x18 (default, configurable via AD0/AD1 pins)

**Key Operations:**
1. **Device Reset:** Initialize DS2482
2. **1-Wire Reset:** Reset 1-Wire bus, check for device presence
3. **Single Bit:** Read/write single bit on 1-Wire bus
4. **Byte Operations:** Read/write full bytes
5. **Strong Pullup:** Enable strong pullup for parasitic power

### 1-Wire Protocol

**Timing:** Controlled by DS2482 (no manual timing needed)

**Commands:**
- **Search ROM (0xF0):** Discover all devices on bus
- **Match ROM (0x55):** Select specific device
- **Skip ROM (0xCC):** Address all devices (single device only)
- **Read ROM (0x33):** Read ROM of single device

**ROM Address:** 64-bit (8 bytes)
- Byte 0: Family code (e.g., 0x28 for DS18B20)
- Bytes 1-6: Serial number
- Byte 7: CRC

### Address Formats

**Raw ROM:** `bytearray([0x28, 0xFF, 0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])`

**Hex ID (reversed):** `"28FF123456789ABC"`

**Hardware ID:** `"FF123456789A"` (without family code and CRC)

---

## Usage Example

```python
from boneio.hardware.i2c.bus import SMBus2I2C
from boneio.hardware.onewire import DS2482, OneWireBus

# Initialize I2C bus
i2c = SMBus2I2C(bus_num=2)

# Initialize DS2482 bridge
ds = DS2482(i2c=i2c, address=0x18, active_pullup=False)

# Create OneWire bus
bus = OneWireBus(ds)

# Scan for devices
devices = bus.scan()
print(f"Found {len(devices)} devices:")
for device in devices:
    print(f"  - {device.hex_id} (HW ID: {device.hw_id})")

# Select and communicate with specific device
if devices:
    device = devices[0]
    bus.select(device)
    # ... device-specific commands ...
```

### Temperature Sensor Example

```python
# For DS18B20 temperature sensors
bus.reset()
bus.skip_rom()  # If only one device
bus.write_byte(0x44)  # Convert T command
time.sleep(0.75)  # Wait for conversion

bus.reset()
bus.skip_rom()
bus.write_byte(0xBE)  # Read scratchpad

# Read 9 bytes
data = [bus.read_byte() for _ in range(9)]
temp_raw = (data[1] << 8) | data[0]
temp_celsius = temp_raw / 16.0
print(f"Temperature: {temp_celsius}°C")
```

---

## Compatibility

### API Compatibility

✅ **100% compatible** with previous implementation:
- `DS2482(i2c, address, active_pullup)` - Same constructor
- `OneWireBus(ds2482)` - Same constructor
- `bus.scan()` - Returns list of `OneWireAddress`
- `OneWireAddress.hex_id` - Same format
- `OneWireAddress.hw_id` - Same format

### Behavioral Differences

1. **Logging:** Added debug logging for all I2C operations
2. **Error handling:** Improved exception handling and logging
3. **Type hints:** Full type annotations for Python 3.13+
4. **Search algorithm:** Reimplemented without Adafruit dependencies

---

## Testing

### Syntax Check
```bash
python3 -m py_compile boneio/hardware/onewire/ds2482.py
python3 -m py_compile boneio/hardware/onewire/bus.py
# ✓ Success
```

### Import Test
```python
from boneio.hardware.onewire import DS2482, OneWireBus, OneWireAddress
# ✓ Success (requires smbus2 installed)
```

### Backward Compatibility
```python
from boneio.helper.onewire import DS2482, OneWireBus
# ✓ Success (imports from hardware.onewire)
```

---

## Migration Impact

### Files Changed: 4
1. `boneio/hardware/onewire/__init__.py` - **NEW** (package)
2. `boneio/hardware/onewire/ds2482.py` - **NEW** (450 lines)
3. `boneio/hardware/onewire/bus.py` - **NEW** (370 lines)
4. `boneio/core/config/loader.py` - Updated import

### Files Removed: 2
1. `boneio/helper/onewire/ds2482.py` - Replaced
2. `boneio/helper/onewire/onewire.py` - Replaced

### Dependencies Removed
- `adafruit-circuitpython-busdevice` (transitive)
- `adafruit-circuitpython-onewire` (transitive)

### Code Using OneWire
- `boneio/core/config/loader.py` - DS2482 initialization
- `boneio/sensor/temp/dallas.py` - Dallas temperature sensors
- `boneio/helper/onewire/W1ThermSensor.py` - Custom sensor wrapper

---

## Use Cases in BoneIO

### DS18B20 Temperature Sensors
OneWire is primarily used for DS18B20 digital temperature sensors:
- Multiple sensors on single bus (up to 20)
- Unique 64-bit address per sensor
- Parasitic power mode support
- 0.5°C accuracy, -55°C to +125°C range

### DS2482 Bridge
The DS2482 provides:
- I2C to 1-Wire protocol conversion
- Hardware timing (no software bit-banging)
- Strong pullup for parasitic power
- Multiple device support on single bus

---

## Next Steps

**Etap 3 Status:** OneWire migration complete!

**Remaining in Etap 3:**
- ⏳ Other device drivers (if any)
- ⏳ Sensor abstraction layer

**Next:** Etap 4 - Components (relay → output)

---

## References

- DS2482 Datasheet: I2C to 1-Wire bridge
- 1-Wire Search Algorithm: Maxim/Dallas Semiconductor
- smbus2 Documentation: https://smbus2.readthedocs.io/
- Previous migrations:
  - MCP23017 (see MIGRATION_NOTES_MCP23017.md)
  - PCF8575 (see MIGRATION_NOTES_PCF8575.md)
  - PCA9685 (see MIGRATION_NOTES_PCA9685.md)
