# Hot-Reload: TimePeriod String Fix (Full Audit)

## Problem
Fast-reload (`load_yaml_file() + merge_board_config()`) skips Cerberus validation
(~0.5s vs ~20s). This means **all config values arrive as raw YAML strings**
(e.g. `"5s"`, `"30s"`, `"500ms"`) instead of pre-parsed `TimePeriod` objects.

Any code that calls `.total_milliseconds`, `.total_in_seconds`, or compares
TimePeriod values with numbers will crash or silently fail.

## Root Cause
Comment in `manager.py` L1593-1594:
> Uses fast path: load_yaml_file() + merge_board_config() (~0.5-1s)
> instead of full Cerberus validation (~20s)

## Fixes Applied

### 1. New Helper: `ensure_time_period()` (timeperiod.py)
- Accepts `TimePeriod | str | int | float`
- Returns `TimePeriod` object
- Supports all unit aliases: `us`, `ms`, `s`, `sec`, `min`, `h`, `d`

### 2. Cover Manager (`covers.py`)
- `_configure_cover()`: Normalizes `open_time`, `close_time`,
  `actuator_activation_duration`, `tilt_duration` before passing to constructors

### 3. Cover Components
- `venetian.py` → `update_config_times()`: Uses `ensure_time_period()` for all values
- `time_based.py` → `update_config_times()`: Uses `ensure_time_period()` for all values

### 4. Action Parser (`manager.py`)
Used existing `parse_time_to_ms()` and `parse_time_to_seconds()` helpers:
- `repeat_interval`: `parse_time_to_ms()` — was raw copy, string would break comparisons
- `delay`: `parse_time_to_seconds()` — string silently dropped, never set
- `transition`: `parse_time_to_seconds()` — string caused fallback to 0.0 instead of actual value
- `min_duration` / `max_duration`: `parse_time_to_ms()` — compared with `duration_ms` (number),
  string would crash with `TypeError`
- `repeat_interval` clamping (L1092): `parse_time_to_seconds()` — string / 1000.0 → `TypeError` crash

### 5. Frontend: CoverTable time display
- Replaced hardcoded `${value}ms` with `formatTimeperiod()` in `CoverTable.tsx`
- Now correctly shows `18s` instead of `18000ms`

## Tests
- `tests/unit/core/test_ensure_time_period.py` — 21 Python tests
- `frontend/__tests__/coverHelpers.test.ts` — 53 TypeScript tests
- All 495 existing core tests pass
