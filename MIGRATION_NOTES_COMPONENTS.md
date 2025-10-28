# Migration Notes: Components Structure (Etap 4)

**Date:** 2025-10-22  
**Component:** Components - OUTPUT (relay → output)  
**Migration:** Structural refactoring for better separation of concerns

---

## Overview

Refactored the `relay/` module into a more generic `components/output/` structure to better reflect the actual purpose of these classes. The term "relay" was too specific - these classes handle all types of outputs: relays, switches, lights, PWM devices, etc.

**UPDATE (2025-10-22):** Full migration completed - old `relay/*.py` files removed, all imports updated to use new `components.output` structure. No backward compatibility aliases.

## Changes Made

### 1. New Structure

**Created:**
```
boneio/components/
├── __init__.py
└── output/
    ├── __init__.py
    ├── basic.py (BasicOutput - was BasicRelay)
    ├── gpio.py (GpioOutput - was GpioRelay)
    ├── mcp.py (MCPOutput - was MCPRelay)
    ├── pcf.py (PCFOutput - was PCFRelay)
    └── pca.py (PWMOutput - was PWMPCA)
```

**Removed (full migration):**
```
boneio/relay/
└── __init__.py (deprecation notice only)

Old files removed:
- basic.py ❌
- gpio.py ❌
- mcp.py ❌
- pcf.py ❌
- pca.py ❌
```

### 2. Class Renames

**Mapping:**
| Old Name (relay/) | New Name (components/output/) | Purpose |
|-------------------|-------------------------------|---------|
| `BasicRelay` | `BasicOutput` | Base class for all outputs |
| `GpioRelay` | `GpioOutput` | Direct GPIO control |
| `MCPRelay` | `MCPOutput` | MCP23017 expander output |
| `PCFRelay` | `PCFOutput` | PCF8575 expander output |
| `PWMPCA` | `PWMOutput` | PCA9685 PWM output |

### 3. Full Migration (No Backward Compatibility)

**UPDATE (2025-10-22):** All old files removed, all imports updated.

**File:** `boneio/relay/__init__.py` (deprecation notice only)

```python
"""DEPRECATED: This module has been removed.

All relay classes have been moved to boneio.components.output and renamed:
- BasicRelay → BasicOutput
- GpioRelay → GpioOutput
- MCPRelay → MCPOutput
- PCFRelay → PCFOutput
- PWMPCA → PWMOutput

Please update your imports:
    from boneio.components.output import MCPOutput, BasicOutput, etc.

This module will be removed in a future version.
"""
```

**Result:** All code updated to use new imports!

```python
# Old import (NO LONGER WORKS)
# from boneio.relay import MCPRelay, BasicRelay

# New import (REQUIRED)
from boneio.components.output import MCPOutput, BasicOutput
```

**Files Updated:**
- `boneio/core/config/loader.py` - Updated output_chooser()
- `boneio/cover/cover.py` - Updated type hints
- `boneio/cover/previous.py` - Updated type hints
- `boneio/cover/time_based.py` - Updated type hints
- `boneio/manager.py` - Updated imports and type hints
- `boneio/group/output.py` - Updated imports and inheritance

### 4. Updated Imports in New Files

**All files in `components/output/` now use:**
```python
from boneio.components.output.basic import BasicOutput
```

**Instead of:**
```python
from boneio.relay.basic import BasicRelay
```

---

## Rationale

### Why "Output" instead of "Relay"?

1. **More Generic:** These classes control various output types:
   - Relays (electromechanical switches)
   - Solid-state switches
   - PWM outputs (LEDs, dimmers)
   - Lights
   - Generic switches

2. **Better Semantics:** 
   - `BasicOutput` - any controllable output
   - `PWMOutput` - PWM-based output (not a relay)
   - `GpioOutput` - GPIO-controlled output

3. **Clearer Intent:** The code controls **outputs**, not just relays

4. **Future-Proof:** Easier to add new output types (e.g., `DACOutput`, `ServoOutput`)

### Why "Components"?

1. **Separation of Concerns:**
   - `hardware/` - Low-level drivers (I2C, GPIO expanders)
   - `components/` - High-level components (outputs, inputs, sensors)
   - `core/` - Core infrastructure

2. **Scalability:** Room for future component types:
   - `components/input/` - Input components
   - `components/sensor/` - Sensor components
   - `components/display/` - Display components

3. **Industry Standard:** Common pattern in embedded/IoT frameworks

---

## Migration Impact

### Files Changed: 11

**New files (components/output/):**
1. `__init__.py` - Package exports
2. `basic.py` - BasicOutput (from BasicRelay)
3. `gpio.py` - GpioOutput (from GpioRelay)
4. `mcp.py` - MCPOutput (from MCPRelay)
5. `pcf.py` - PCFOutput (from PCFRelay)
6. `pca.py` - PWMOutput (from PWMPCA)

**Modified files (relay/):**
1. `__init__.py` - Backward compatibility re-exports

**Created:**
1. `components/__init__.py` - Package marker
2. `relay/basic_compat.py` - Compatibility helper

### Files Kept: 5

**Original files in `relay/` kept for now:**
- `basic.py` - Still used by cover components
- `gpio.py` - Original implementation
- `mcp.py` - Original implementation
- `pcf.py` - Original implementation
- `pca.py` - Original implementation

**Reason:** Gradual migration approach. These will be removed in future when all references are updated.

### Code Using Relay Classes

**Files that import from `boneio.relay`:**
- `boneio/core/config/loader.py` - Creates relay instances
- `boneio/cover/cover.py` - Uses BasicRelay
- `boneio/cover/previous.py` - Uses BasicRelay
- `boneio/cover/time_based.py` - Uses BasicRelay
- `boneio/group/output.py` - Groups relays
- `boneio/manager.py` - Manages relays

**Status:** All continue to work via backward compatibility re-exports.

---

## API Compatibility

### 100% Backward Compatible

✅ **Old imports still work:**
```python
from boneio.relay import MCPRelay, BasicRelay, PWMPCA
```

✅ **Old class names still work:**
```python
relay = MCPRelay(pin=0, mcp=mcp_instance, mcp_id="mcp1")
```

✅ **All methods unchanged:**
```python
relay.turn_on()
relay.turn_off()
relay.is_active
```

### New Recommended Usage

```python
# New imports
from boneio.components.output import MCPOutput, BasicOutput, PWMOutput

# New class names (same API)
output = MCPOutput(pin=0, mcp=mcp_instance, mcp_id="mcp1")
output.turn_on()
```

---

## Testing

### Syntax Check
```bash
python3 -m py_compile boneio/components/output/*.py
# ✓ Success
```

### Import Test
```python
# Old imports (backward compatibility)
from boneio.relay import MCPRelay, BasicRelay, PWMPCA
# ✓ Success

# New imports
from boneio.components.output import MCPOutput, BasicOutput, PWMOutput
# ✓ Success
```

### Alias Test
```python
from boneio.relay import MCPRelay
from boneio.components.output import MCPOutput

# MCPRelay is an alias for MCPOutput
assert MCPRelay is MCPOutput  # ✓ True
```

---

## Future Work

### Phase 1: Gradual Migration (Current)
- ✅ Create new structure in `components/output/`
- ✅ Provide backward compatibility in `relay/`
- ✅ Keep both versions working

### Phase 2: Update Internal Code (Future)
- Update `core/config/loader.py` to use new imports
- Update `cover/` components to use `BasicOutput`
- Update `group/output.py` to use new names

### Phase 3: Deprecation (Future)
- Add deprecation warnings to `relay/` imports
- Update documentation to recommend new imports

### Phase 4: Cleanup (Far Future)
- Remove old `relay/` files (except `__init__.py`)
- Keep `relay/__init__.py` as permanent compatibility layer

---

## Benefits

### 1. Better Code Organization
- Clear separation: `hardware/` vs `components/`
- Logical grouping of related functionality
- Easier to navigate codebase

### 2. More Accurate Naming
- `Output` better describes purpose than `Relay`
- `PWMOutput` more accurate than `PWMPCA`
- `BasicOutput` clearer than `BasicRelay`

### 3. Future Extensibility
- Easy to add new component types
- Room for `components/input/`, `components/sensor/`, etc.
- Scalable architecture

### 4. Zero Breaking Changes
- 100% backward compatible
- Old code continues to work
- Gradual migration possible

---

## Comparison with Other Frameworks

### Home Assistant
```python
homeassistant/components/
├── light/
├── switch/
├── cover/
└── sensor/
```

### ESPHome
```python
esphome/components/
├── output/
├── light/
├── switch/
└── sensor/
```

### BoneIO (Now)
```python
boneio/components/
└── output/  # ✅ Aligned with industry patterns
```

---

## Summary

**Etap 4 Status:** ✅ COMPLETED

**Changes:**
- Created `components/output/` structure
- Renamed classes for clarity (Relay → Output)
- Maintained 100% backward compatibility
- Zero breaking changes

**Statistics:**
- New files: 8
- Modified files: 1
- Lines of code: ~500 (copied + modified)
- Breaking changes: 0
- API compatibility: 100%

**Next Steps:**
- Etap 5: Integration (HA discovery, interlock)
- Future: Gradual migration of internal code to new imports

---

## References

- Previous migrations:
  - MCP23017 (see MIGRATION_NOTES_MCP23017.md)
  - PCF8575 (see MIGRATION_NOTES_PCF8575.md)
  - PCA9685 (see MIGRATION_NOTES_PCA9685.md)
  - OneWire (see MIGRATION_NOTES_ONEWIRE.md)
