# GPIO Long Press Fix — Missed RELEASE Edge Detection

## Problem
GPIO inputs sometimes miss `RISING_EDGE` events (EMI, kernel bugs on BeagleBone),
causing infinite periodic long press events. Observed: 57+ seconds of periodic
long events on `PRW_1_50L (P8_13)` with duration growing indefinitely.

## Root Cause
- Linux kernel `gpiod` occasionally drops edge events
- The only safety was `max_long_press_seconds` = 120s — far too long
- No physical GPIO state verification during long press

## Changes

### 1. max_long_press_seconds: 120s → 30s (hard max)
| Component | Before | After |
|---|---|---|
| `MultiClickDetector.__init__` default | 120.0 | 30.0 |
| `event.py` default | 120 * 1000 | 30 * 1000 |
| `event.py` hard clamp | none | min(value, 30.0) |
| `schema.yaml` default | `120s` | `30s` |
| `EventForm.tsx` maximum | 600000ms | 30000ms |
| `EventForm.tsx` default | `120s` | `30s` |
| `RemoteInputForm.tsx` maximum | 600000ms | 30000ms |
| `RemoteInputForm.tsx` default | `120s` | `30s` |

### 2. GPIO Readback (new feature)
Every 3 seconds during a long press, the detector reads the physical GPIO
pin state via `gpiod.LineRequest.get_values()`. If the pin is HIGH (= button
released with pull-up), but no `RISING_EDGE` was received, the long press
is force-stopped immediately.

**Architecture:**
- `MultiClickDetector` gets `_gpio_readback_fn: Callable[[], bool | None]`
- `GpioManager._install_gpio_readback()` creates closures per detector
- Called from `_seed_initial_states()` after GPIO lines are configured

### 3. Debug Logging
Extensive `_LOGGER.debug()` added throughout the long press flow:
- `_detect_long_press` entry/exit
- `_send_periodic_long_event` skip reasons
- GPIO readback results (HIGH/LOW)
- Readback failures

## Files Changed
- `boneio/components/input/detectors.py` — detector logic
- `boneio/components/input/event.py` — default value changes
- `boneio/hardware/gpio/input/manager.py` — readback installation
- `boneio/schema/schema.yaml` — schema defaults
- `frontend/src/components/UISettings/EventForm.tsx` — UI defaults
- `frontend/src/components/UISettings/RemoteInputForm.tsx` — UI defaults
