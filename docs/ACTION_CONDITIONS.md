# Action Conditions System

## Overview

The action conditions system allows boneIO actions (button presses, events) to execute
conditionally based on **time**, **date**, or **entity state**.

## Architecture

The system is split into two layers for performance:

### 1. Compile-time (`parse_actions`)

When the config is loaded, each action's `condition` / `conditions` dict is **pre-compiled**
into Python objects (`_TimeCondition`, `_DateCondition`, `_StateCondition`, `_ConditionGroup`).
The compiled object is stored on the action dict as `_compiled_conditions`.

**Module**: `boneio/core/manager/action_conditions.py`

### 2. Evaluation-time (`execute_actions`)

At button-press time, conditions are evaluated via `should_execute_action()`:

- `datetime.now()` is called **once** per `execute_actions` batch and shared
  across all actions — avoids per-action overhead.
- Pre-compiled conditions skip all dict-based string parsing.
- State conditions use a `state_resolver` callback.

### Logger

All condition-related logs use the **`boneio.action_conditions`** logger
(not the generic `boneio.core.manager`), making them easy to filter:

```yaml
logger:
  logs:
    boneio.action_conditions: debug
```

## Condition Types

### Time condition
```yaml
condition:
  type: time
  after: "05:00"
  before: "22:00"
```
Supports midnight crossover: `after: "22:00"`, `before: "06:00"`.

### Date condition
```yaml
condition:
  type: date
  after: "11-01"
  before: "03-31"
```
Supports new year crossover.

### State condition
```yaml
condition:
  type: state
  entity: output
  entity_id: lamp_hallway
  state: is_on
```
`state` values: `is_on`, `is_off`, `is_open`, `is_closed`.

### Multiple conditions (AND/OR)
```yaml
conditions:
  mode: and  # or "or"
  list:
    - type: time
      after: "06:00"
      before: "23:00"
    - type: state
      entity: output
      entity_id: lamp_hallway
      state: is_on
```

## Entity State Resolution

The `state_resolver` maps `entity_type` to the appropriate manager lookup:

| `entity` (config) | Manager method | Object class | Key property |
|---|---|---|---|
| `output` / `light` | `outputs.get_output(id)` | `BasicOutput` | `is_active` (bool) |
| `cover` | `covers.get_cover(id)` | `BaseCover` | `is_open` (bool) |
| `binary_sensor` | `inputs.get_input(id)` | `GpioBaseClass` | `is_active` (bool) |

All lookups are **O(1) dict.get()** — no iteration.

### State keywords mapping

| Config `state` | Property checked |
|---|---|
| `is_on` | `entity.is_active == True` |
| `is_off` | `entity.is_active == False` |
| `is_open` | `entity.is_open == True` (covers) |
| `is_closed` | `entity.is_open == False` (covers) |

## Files Changed

| File | Change |
|---|---|
| `boneio/core/manager/action_conditions.py` | **New** — pre-compiled condition evaluation |
| `boneio/core/manager/manager.py` | Use pre-compiled conditions, `datetime.now()` once per batch |
| `boneio/hardware/gpio/input/base.py` | **Bugfix** — added `is_active` property (was missing for binary sensors) |
| `boneio/components/cover/cover.py` | **Bugfix** — added `is_open` property (was missing for covers) |
| `boneio/core/utils/conditions.py` | Kept — still used for backend validation API |
