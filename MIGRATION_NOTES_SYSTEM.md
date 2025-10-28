# Migration Notes: System Monitoring Module

## Overview

Moved system monitoring and host data functionality from `helper/stats.py` to `core/system/` for better organization and future Web UI integration.

## Changes

### New Structure

```
core/
└── system/
    ├── __init__.py          # Public API exports
    ├── monitor.py           # System monitoring functions
    └── host_data.py         # HostData & HostSensor classes
```

### Files Created

1. **`core/system/monitor.py`** - System monitoring utilities:
   - `display_time()` - Format seconds to human-readable string
   - `get_network_info()` - Fetch eth0 network info (IP, mask, MAC)
   - `get_cpu_info()` - CPU usage statistics
   - `get_disk_info()` - Disk usage for root partition
   - `get_memory_info()` - RAM usage statistics
   - `get_swap_info()` - Swap usage statistics
   - `get_uptime()` - System uptime

2. **`core/system/host_data.py`** - Display data aggregation:
   - `HostSensor` - Async updater for system stats
   - `HostData` - Aggregates system data for OLED/Web UI

3. **`core/system/__init__.py`** - Public API

### Files Modified

| File | Change |
|------|--------|
| `hardware/display/oled.py` | `from boneio.helper.stats import HostData` → `from boneio.core.system import HostData` |
| `runner.py` | `from boneio.helper.stats import get_network_info` → `from boneio.core.system import get_network_info` |
| `sensor/serial_number.py` | `from boneio.helper.stats import get_network_info` → `from boneio.core.system import get_network_info` |
| `helper/__init__.py` | Added backward compatibility re-exports |

### Files Deleted

- ❌ `helper/stats.py` (372 lines) - Split into `monitor.py` + `host_data.py`

## Migration Guide

### For New Code

```python
# ✅ Recommended - Import from core.system
from boneio.core.system import (
    HostData,
    HostSensor,
    get_cpu_info,
    get_disk_info,
    get_memory_info,
    get_network_info,
    get_swap_info,
    get_uptime,
    display_time,
)
```

### For Legacy Code (Backward Compatible)

```python
# ✅ Still works - backward compatibility maintained
from boneio.helper import HostData, get_network_info
```

## Benefits

### 1. Better Organization
- System monitoring functions separated from display logic
- Clear separation: `monitor.py` (data collection) vs `host_data.py` (data aggregation)

### 2. Reusability
- Monitoring functions can be used by:
  - OLED display (current)
  - Web UI (future)
  - REST API endpoints (future)
  - CLI tools (future)

### 3. Improved Documentation
- Each function has detailed docstrings
- Type hints for all parameters and returns
- Examples in docstrings

### 4. Future-Proof
- Easy to add new monitoring functions
- Ready for Web UI integration
- Can be exposed via REST API

## Usage Examples

### Basic System Monitoring

```python
from boneio.core.system import (
    get_cpu_info,
    get_memory_info,
    get_network_info,
)

# Get current stats
cpu = get_cpu_info()
# {'total': '45%', 'user': '30.5%', 'system': '14.5%'}

memory = get_memory_info()
# {'total': '512MB', 'used': '256MB', 'free': '256MB'}

network = get_network_info()
# {'ip': '192.168.1.100', 'mask': '255.255.255.0', 'mac': 'aa:bb:cc:dd:ee:ff'}
```

### For OLED Display

```python
from boneio.core.system import HostData

# Create host data aggregator
host_data = HostData(
    output=output_devices,
    inputs=input_devices,
    temp_sensor=temp_sensor,
    ina219=ina219_sensor,
    manager=manager,
    event_bus=event_bus,
    enabled_screens=['cpu', 'memory', 'network'],
    extra_sensors=[],
)

# Get formatted data for display
cpu_data = host_data.get('cpu')
network_data = host_data.get('network')
```

### For Future Web UI

```python
from boneio.core.system import get_cpu_info, get_memory_info, get_disk_info

@app.get("/api/system/stats")
async def get_system_stats():
    """REST API endpoint for system statistics."""
    return {
        "cpu": get_cpu_info(),
        "memory": get_memory_info(),
        "disk": get_disk_info(),
    }
```

## Testing

All monitoring functions can be tested independently:

```python
from boneio.core.system import monitor

# Test individual functions
assert 'total' in monitor.get_cpu_info()
assert 'ip' in monitor.get_network_info()
assert monitor.display_time(3661) == "1h1m"
```

## Notes

- All monitoring functions use `psutil` library
- Network info is fetched from `eth0` interface
- Disk usage is for root partition `/`
- Uptime uses `time.CLOCK_BOOTTIME`
- All values are formatted as strings with units (%, MB, GB)

## Backward Compatibility

✅ **100% backward compatible**

Old imports still work through `helper/__init__.py` re-exports:
```python
from boneio.helper import HostData  # Still works!
```

## Future Enhancements

Possible additions to `core/system/`:

1. **`monitor.py`**:
   - `get_temperature_info()` - CPU temperature
   - `get_process_info()` - Running processes
   - `get_network_traffic()` - Network I/O stats

2. **`alerts.py`**:
   - Threshold monitoring
   - Alert triggers for high CPU/memory

3. **`history.py`**:
   - Historical data storage
   - Time-series data for graphs

## Related Files

- `hardware/display/oled.py` - Uses HostData for OLED display
- `sensor/serial_number.py` - Uses get_network_info() for MAC address
- `runner.py` - Uses get_network_info() for network detection
- `models.py` - Defines HostSensorState model

## Summary

✅ Moved from `helper/stats.py` to `core/system/`
✅ Split into `monitor.py` (functions) + `host_data.py` (classes)
✅ 100% backward compatibility maintained
✅ Better documentation and type hints
✅ Ready for Web UI integration
✅ 4 files updated, 1 file deleted, 3 files created
