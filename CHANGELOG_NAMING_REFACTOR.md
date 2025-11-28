# Changelog: Output/Input Naming Refactor

## Overview

This refactor introduces a cleaner separation between technical identifiers and display names for outputs, inputs, and related components.

## Version: 2.0.0 (Breaking Change)

### Changes

#### Output Configuration

**Before:**
```yaml
output:
  - id: swiatlo_kuchnia        # Used as both ID and display name
    boneio_output: OUT_01
    output_type: light
```

**After:**
```yaml
output:
  - boneio_output: OUT_01      # Technical ID (used in MQTT, groups, actions)
    name: "Światło kuchnia"    # Optional display name
    output_type: light

  # Or with custom ID override:
  - boneio_output: OUT_01
    id: custom_id              # Overrides boneio_output as ID
    name: "Światło kuchnia"
    output_type: light
```

#### ID Resolution Logic

```python
effective_id = output.get('id') or output.get('boneio_output')
```

Priority:
1. `id` (if provided) - overrides boneio_output
2. `boneio_output` - default ID when boneio section exists
3. `id` required - when no boneio section (legacy devices)

#### Output Groups

**Before:**
```yaml
output_group:
  - id: group1
    outputs:
      - swiatlo_kuchnia    # Referenced by id field
      - swiatlo_salon
```

**After:**
```yaml
output_group:
  - id: group1
    name: "Grupa świateł"
    outputs:
      - OUT_01             # Referenced by boneio_output (or custom id)
      - OUT_02
```

#### MQTT Topics

**Before:**
```
boneio/{boneio_id}/light/{id}/state
boneio/{boneio_id}/light/swiatlo_kuchnia/state
```

**After:**
```
boneio/{boneio_id}/light/{effective_id}/state
boneio/{boneio_id}/light/OUT_01/state
# Or with custom id:
boneio/{boneio_id}/light/custom_id/state
```

#### Actions in Events

**Before:**
```yaml
event:
  - boneio_input: IN_01
    actions:
      single:
        - action: output
          pin: swiatlo_kuchnia    # Referenced by id
```

**After:**
```yaml
event:
  - boneio_input: IN_01
    actions:
      single:
        - action: output
          pin: OUT_01             # Referenced by effective_id (boneio_output or id)
```

### Migration Guide

#### For users with `boneio` section (new devices):

1. **Remove `id` field** if it's the same as `boneio_output`:
   ```yaml
   # Before
   - id: OUT_01
     boneio_output: OUT_01
   
   # After
   - boneio_output: OUT_01
   ```

2. **Rename `id` to `name`** if you want a display name:
   ```yaml
   # Before
   - id: swiatlo_kuchnia
     boneio_output: OUT_01
   
   # After
   - boneio_output: OUT_01
     name: "Światło kuchnia"
   ```

3. **Keep `id`** only if you need a custom technical identifier:
   ```yaml
   - boneio_output: OUT_01
     id: kitchen_light        # Custom ID for MQTT/groups/actions
     name: "Światło kuchnia"  # Display name
   ```

4. **Update output_group references** to use `boneio_output` values:
   ```yaml
   output_group:
     - id: lights_group
       outputs:
         - OUT_01    # Was: swiatlo_kuchnia
         - OUT_02    # Was: swiatlo_salon
   ```

5. **Update action references** in events:
   ```yaml
   actions:
     single:
       - action: output
         pin: OUT_01    # Was: swiatlo_kuchnia
   ```

#### For users without `boneio` section (legacy devices):

No changes required. `id` field remains required.

### Benefits

1. **Stable identifiers** - `boneio_output` doesn't change, safe to use in groups/actions
2. **Flexible naming** - Change `name` without breaking references
3. **Cleaner config** - Less redundancy when id = boneio_output
4. **Consistent** - Same pattern for outputs, inputs, events

### Files Changed

#### Backend
- `boneio/schema/schema.yaml` - Updated field definitions and descriptions
- `boneio/core/manager/outputs.py` - ID resolution logic (already implemented):
  ```python
  # Priority: id > boneio_output > name (slugified)
  if ID in config_copy:
      _id = config_copy.pop(ID)
  elif "boneio_output" in config_copy:
      _id = config_copy.get("boneio_output")
  else:
      _id = strip_accents(_name)
  ```

#### Frontend
- `frontend/src/components/UISettings/OutputGroupForm.tsx` - Added `name` field, updated descriptions
- `frontend/src/components/UISettings/ArrayTableWidget.tsx` - Updated validation and table display

---

## Future: Input/Event Refactor (Planned)

Same pattern will be applied to:
- `binary_sensor` - `boneio_input` as default ID
- `event` - `boneio_input` as default ID

