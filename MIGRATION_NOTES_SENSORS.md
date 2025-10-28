## Migration Notes: Temperature Sensors

## Overview

Moved temperature sensor classes from `sensor/temp/` to `hardware/sensor/temperature/` for better organization and separation of hardware drivers from high-level components.

## Changes

### New Structure

```
hardware/sensor/temperature/
├── __init__.py          # Public API exports
├── base.py              # TempSensor base class
├── dallas.py            # Dallas 1-Wire sensors (DS18B20, etc.)
├── lm75.py              # LM75 I2C temperature sensor
└── mcp9808.py           # MCP9808 I2C temperature sensor
```

### Files Created

1. **`hardware/sensor/temperature/base.py`** - Base class for all temperature sensors:
   - `TempSensor` - Abstract base with MQTT, AsyncUpdater, and Filter support
   - Common functionality for all temperature sensors
   - Event bus integration
   - Periodic updates

2. **`hardware/sensor/temperature/dallas.py`** - Dallas 1-Wire sensor:
   - Supports DS18B20, DS18S20, DS1822, etc.
   - Lazy import of w1thermsensor (avoids kernel module loading)
   - Async executor for blocking get_temperature() calls
   - Better error handling

3. **`hardware/sensor/temperature/lm75.py`** - LM75 I2C sensor:
   - Uses PCT2075 driver (register-compatible)
   - Temperature range: -55°C to +125°C
   - Resolution: 0.125°C

4. **`hardware/sensor/temperature/mcp9808.py`** - MCP9808 I2C sensor:
   - High-accuracy sensor (±0.25°C)
   - Resolution: 0.0625°C (12-bit)
   - Commonly used for board temperature monitoring

### Files Modified

| File | Change |
|------|--------|
| `manager.py` | `from boneio.sensor.temp import TempSensor` → `from boneio.hardware.sensor.temperature import TempSensor` |
| `core/system/host_data.py` | `from boneio.sensor.temp import TempSensor` → `from boneio.hardware.sensor.temperature import TempSensor` |
| `core/config/loader.py` | `from boneio.sensor import LM75Sensor` → `from boneio.hardware.sensor.temperature import LM75Sensor` |
| `sensor/__init__.py` | Added backward compatibility re-exports |
| `hardware/sensor/__init__.py` | Added temperature sensor exports |

### Files Deleted

- ❌ `sensor/temp/` - Entire directory removed (no backward compatibility)

## Migration Guide

### For New Code

```python
# ✅ Recommended - Import from hardware.sensor.temperature
from boneio.hardware.sensor.temperature import (
    TempSensor,
    DallasSensor,
    LM75Sensor,
    MCP9808Sensor,
)
```

### Breaking Changes

```python
# ❌ NO LONGER WORKS - old imports removed
from boneio.sensor import DallasSensor, LM75Sensor, MCP9808Sensor  # ❌
from boneio.sensor.temp import TempSensor  # ❌

# ✅ Use new imports instead
from boneio.hardware.sensor.temperature import (
    DallasSensor,
    LM75Sensor,
    MCP9808Sensor,
    TempSensor,
)
```

## Benefits

### 1. Better Organization
- Hardware drivers separated from high-level components
- Clear hierarchy: `hardware/sensor/temperature/`
- Consistent with other hardware modules (gpio, i2c, onewire)

### 2. Improved Documentation
- Each sensor has detailed docstrings
- Type hints for all parameters
- Usage examples in docstrings

### 3. Better Error Handling
- Dallas sensor: Lazy import of w1thermsensor
- Async executor for blocking calls
- Specific exception types

### 4. Future-Proof
- Ready for additional temperature sensors
- Easy to add new sensor types
- Consistent API across all sensors

## Sensor Details

### Dallas 1-Wire Sensors

**Supported models:**
- DS18B20 (most common)
- DS18S20
- DS1822
- DS28EA00
- MAX31850K

**Features:**
- 1-Wire protocol (single data line)
- Unique 64-bit ROM ID
- Parasitic power mode support
- Temperature range: -55°C to +125°C
- Resolution: 9-12 bit (configurable)

**Example:**
```python
sensor = DallasSensor(
    address='28-0000098c7df0',
    id='living_room_temp',
    filters=['round(x, 2)'],
    manager=manager,
    update_interval=TimePeriod(seconds=60)
)
```

### LM75 I2C Sensor

**Features:**
- I2C interface (address: 0x48-0x4F)
- Temperature range: -55°C to +125°C
- Accuracy: ±2°C (typical)
- Resolution: 0.125°C

**Example:**
```python
sensor = LM75Sensor(
    i2c=i2c_bus,
    address=0x48,
    id='room_temp',
    manager=manager,
    update_interval=TimePeriod(seconds=30)
)
```

### MCP9808 I2C Sensor

**Features:**
- I2C interface (address: 0x18-0x1F)
- Temperature range: -40°C to +125°C
- Accuracy: ±0.25°C (typical)
- Resolution: 0.0625°C (12-bit)
- Low power consumption

**Example:**
```python
sensor = MCP9808Sensor(
    i2c=i2c_bus,
    address=0x18,
    id='board_temp',
    manager=manager,
    update_interval=TimePeriod(seconds=30)
)
```

## Testing

All sensors can be tested independently:

```python
from boneio.hardware.sensor.temperature import DallasSensor, LM75Sensor

# Test Dallas sensor
dallas = DallasSensor(address='28-0000098c7df0', ...)
assert dallas.state is not None

# Test LM75 sensor
lm75 = LM75Sensor(i2c=i2c_bus, address=0x48, ...)
assert lm75.unit_of_measurement == "°C"
```

## Notes

- All sensors inherit from `TempSensor` base class
- MQTT integration is built-in
- Event bus integration for real-time updates
- Filters can be applied to readings (e.g., rounding)
- Async updates prevent blocking the event loop

## Breaking Changes

❌ **NO backward compatibility**

Old imports have been removed. You must update your code:
```python
# Old (removed):
from boneio.sensor.temp import TempSensor
from boneio.sensor import DallasSensor

# New (required):
from boneio.hardware.sensor.temperature import TempSensor, DallasSensor
```

## Future Enhancements

Possible additions to `hardware/sensor/temperature/`:

1. **DHT22** - Humidity + temperature sensor
2. **BME280** - Pressure + humidity + temperature
3. **SHT31** - High-accuracy humidity + temperature
4. **TMP117** - Ultra-high-accuracy I2C sensor

## Related Files

- `manager.py` - Uses TempSensor for type hints
- `core/system/host_data.py` - Uses TempSensor for OLED display
- `core/config/loader.py` - Creates temperature sensor instances
- `models.py` - Defines SensorState model

## Summary

✅ Moved from `sensor/temp/` to `hardware/sensor/temperature/`
✅ Created base class with common functionality
✅ Improved documentation and type hints
❌ NO backward compatibility - clean break
✅ Ready for additional sensor types
✅ 5 files updated, 4 files created, 1 directory deleted

**Breaking change:** All code must update imports to new location.
