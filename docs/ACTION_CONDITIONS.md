# Action Conditions System

## Overview

The action conditions system allows boneIO actions (button presses, events) to execute
conditionally based on **time**, **date**, **entity state**, or the **position of the
Sun**. Entity state includes **virtual switches** — flags with no hardware behind
them, flipped from Home Assistant or another action; see `docs/VIRTUAL_SWITCHES.md`.

## Architecture

The system is split into two layers for performance:

### 1. Compile-time (`parse_actions`)

When the config is loaded, each action's `condition` / `conditions` dict is **pre-compiled**
into Python objects (`_TimeCondition`, `_DateCondition`, `_StateCondition`, `_ConditionGroup`).
The compiled object is stored on the action dict as `_compiled_conditions`.

**Module**: `boneio/core/manager/action_conditions.py`

### 2. Evaluation-time (`execute_actions`)

At button-press time, conditions are evaluated via `should_execute_action()`:

- `datetime.now().astimezone()` is called **once** per `execute_actions` batch
  and shared across all actions — avoids per-action overhead. It is *aware*:
  sun anchors are born as aware UTC, and comparing them against a naive local
  time would be ambiguous in the hour the clock goes back. `.time()` and
  `.month` behave identically on an aware local datetime, so the time and date
  conditions are unaffected.
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

### Sun condition

Needs the `location:` section — see `docs/SUN.md`. One of three shapes, never a
mixture; the loader and the web UI both refuse a condition that mixes them.

**A window between two sun anchors.** `after`/`before` name anchors instead of
clock times, and each takes an optional offset (negative is earlier):

```yaml
condition:
  type: sun
  after: sunset
  after_offset: "-15min"
  before: civil_dawn
```

A `sunset → sunrise` window wraps past midnight, exactly as `22:00 → 06:00`
does for a time condition.

**A phase of the day:**

```yaml
condition:
  type: sun
  phase: golden_hour
```

`day`, `civil_twilight`, `nautical_twilight`, `astronomical_twilight`, `night`,
plus the two photographic bands `golden_hour` (-4°…+6°) and `blue_hour`
(-6°…-4°) which *overlap* the others rather than sitting between them.

**An elevation band,** in degrees above the horizon:

```yaml
condition:
  type: sun
  above: 0
  below: 10
```

#### Where an anchor does not exist

Above roughly 60° of latitude the Sun may not cross a given angle at all on a
given day, so the anchor has no time. The bound then collapses to the start or
the end of the local day, chosen by which side the Sun stayed on:

| Situation | `sunrise` resolves to | `sunset` resolves to | `sunrise → sunset` means |
|---|---|---|---|
| Polar day | start of day | end of day | the whole day |
| Polar night | end of day | start of day | nothing |

Which makes `sunset → sunrise` behave the other way round, as it should. The
`horizon_state` field of `GET /api/sun/today` reports the same thing to the
panel.

#### When the Sun's position is unknown

No `location:`, or a clock that has not been set yet (the board has no RTC):
the condition evaluates to **true** and logs once. That matches how every other
condition treats a configuration error — it does not block the action — but it
does mean a sun condition can silently stop gating anything, which is why the
web UI refuses to save one on a device with no coordinates.

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

Sun conditions mix freely with the rest:

```yaml
conditions:
  mode: and
  list:
    - type: sun
      after: sunset
      before: sunrise
    - type: date
      after: "10-01"
      before: "04-30"
```

## Entity State Resolution

The `state_resolver` maps `entity_type` to the appropriate manager lookup:

| `entity` (config) | Manager method | Object class | Key property |
|---|---|---|---|
| `output` / `light` | `outputs.get_output(id)` | `BasicOutput` | `is_active` (bool) |
| `virtual_switch` | `virtual_switches.get(id)` | `VirtualSwitch` | `is_active` (bool) |
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
| `boneio/core/utils/conditions.py` | The straightforward reference implementation. The running device does not use it; sun conditions there *delegate* to the compiled class rather than reimplementing the polar rules |
| `boneio/core/manager/sun.py` | `SunProvider` — the location, the timezone, and a day of cached anchors |
| `boneio/core/utils/sun.py` | The solar maths. See `docs/SUN.md` |
| `boneio/schema/condition.yaml` | `sun` type, anchors, offsets, phases, elevations, and the `condition_shape` check |
| `boneio/core/config/yaml_util.py` | `sun_offset` coercion (signed, in seconds) and `_check_with_condition_shape` |
| `boneio/webui/action_validation.py` | Refuses a sun condition on a device with no `location:` |

## Performance

A sun condition costs two dict lookups and two datetime comparisons on the hot
path. The anchors it reads are computed once per local day by `SunProvider` and
reused; elevation readings are cached for 60 s. The only case that computes
anything per evaluation is a *missing* anchor at high latitude, which needs one
`threshold_state` call to decide which way the window collapses.

## `probability` — running an action only some of the time

Not a condition, but it sits in the same place: after the conditions have
passed, before the action runs.

```yaml
actions:
  - action: output
    boneio_output: out_livingroom
    action_output: "ON"
    probability: 0.7      # seven times out of ten
```

Drawn per firing, and drawn *after* the conditions — a `probability` on an
action whose condition is false still never runs, and the draw is not burned on
a firing that was never going to happen.

Written for presence simulation, where `jitter` on a schedule randomises *when*
a step happens and this randomises *whether*. That is the difference between
lights on a timer and somebody living there: three evenings of the same four
steps is a pattern an observer can read. See
[PRESENCE_SIMULATION.md](PRESENCE_SIMULATION.md).
