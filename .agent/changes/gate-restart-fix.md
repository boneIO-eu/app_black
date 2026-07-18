# Gate Opening on Restart Bug Fix

## Problem
When the boneIO application restarts, gate covers (bramy) would automatically open because:

1. Binary sensors with `initial_send=True` publish their current state on startup
2. These events go through `handle_input_event` with `publish_only=True`
3. **BUG**: `on_input_event` was called BEFORE the `publish_only` check, routing
   initial state sync events to gate covers
4. Gate cover's `on_sensor_event` interpreted the state change and published a new
   state to MQTT
5. Home Assistant received the state change and could trigger automations (e.g., "when gate opens")

## Root Cause
In `inputs.py` `handle_input_event`:
```python
# This was intentionally placed BEFORE publish_only check (see old comment)
self._manager.templates.on_input_event(event.entity_id, event.click_type)

# But this meant publish_only events still triggered gate cover state changes!
if event.publish_only:
    return
```

Additionally, `_sync_gate_initial_state` in `GateCoverManager` used 
`send_current_state_for_input()` which fired EventBus events that went through 
the same buggy path.

## Fix

### 1. Move `publish_only` check before template routing (`inputs.py`)
```python
if event.publish_only:
    return  # Skip BOTH actions AND template routing

self._manager.templates.on_input_event(event.entity_id, event.click_type)
```

### 2. Replace event-based initial sync with direct state read (`gate_cover.py`)
Instead of firing events through EventBus, `GateCoverManager._sync_initial_state()` 
now reads `sensor.is_active` directly from the binary sensor instance.

### 3. Move sync to `start()` time (`templates/__init__.py`)
Initial state sync is now called during `TemplateManager.start()` (when GPIO manager 
is running and sensors have correct state), not during `configure()` (when GPIO may 
not be ready yet).

## Files Changed
- `boneio/core/manager/inputs.py` — publish_only check moved before template routing
- `boneio/core/manager/templates/__init__.py` — sync_initial_state called at start() time
- `boneio/core/manager/templates/gate_cover.py` — _sync_initial_state reads sensor directly
- `boneio/components/template/gate_cover.py` — simplified start(), removed dead code
