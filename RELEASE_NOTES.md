# boneIO v1.4.0dev1 — Release Notes

## ✨ New Features

### Remote Outputs (`remote_outputs` section)
Register switches and lights from remote ESPHome/MQTT devices as first-class outputs in boneIO.  
Outputs appear in the WebUI with full ON/OFF/TOGGLE control and area assignment.

### Brightness Control for Remote ESPHome Lights
If an ESPHome light supports brightness, the remote output gains a **brightness slider** in the WebUI.
- Real-time synchronization: changes from Home Assistant or ESPHome reflect live in the boneIO frontend
- Smooth animated slider transitions (ease-out cubic, 250ms) for server-driven value updates
- Debounced API calls with 800ms cooldown to prevent race-condition "jump-back" artifacts

### Remote Binary Sensors (ESPHome)
Subscribe to binary sensors on ESPHome devices and use them as triggers for boneIO actions.
- Only sensors with registered callbacks are logged (reduces noise from unrelated ESPHome entities)
- Callback-based architecture: `register_binary_sensor_callback()` / `unregister_binary_sensor_callback()`

### Remote Inputs Refactor
Unified local and remote input handling with consistent state management and alarm integration.
- Remote devices can now trigger alarm panel actions

### WLED Brightness Support
Merged PR #65 — WLED devices now support brightness control via the remote device API.

### OLED Display Improvements
- Added OLED display tests
- Fixed OLED sleep behavior on single click
- Cover change settings via OLED display

### Modbus Device Temporary Disable
Added the ability to temporarily turn off a single Modbus device without removing its configuration.

## 🐛 Bug Fixes

### Frontend — Brightness State Not Updating
WebSocket output deduplication compared only `state` (ON/OFF) and `name`, ignoring `brightness`.  
Brightness changes on a light that was already ON were silently discarded.

### Frontend — MQTT Discovery Shows 0 Outputs/Covers
Backend nests outputs/covers under `mqtt` key in `to_dict()`, but frontend read top-level fields.  
All MQTT autodiscovered devices showed "0 out | 0 cov" despite having many entities.

### Frontend — Slider Jump-Back on Brightness Change
After user set brightness, slider briefly jumped back to the old value before settling.  
Root cause: `isActive` flag cleared immediately after API call, allowing stale ESPHome callbacks through.

### Backend — Entity Type Routing in ESPHome
`control_output()` always delegated to `control_switch()` — failed for light entities.  
Now auto-detects entity type by checking `_switches` then `_lights`.

### Backend — Connect Before Entity Lookup
`control_switch()` and `control_light()` looked up entity keys before `connect()`.  
If `_on_entities()` hadn't run yet, entity lists were empty.

### Backend — Remote Output Lazy Resolution
`register_remote_outputs()` was called during `Manager.__init__()` before device connections were established.  
`get_device()` returned `None` → all remote outputs were silently skipped.

### Input Selection — Case Sensitivity
Fixed inputs not appearing in selection dropdown when named with capital letters.

### Help Label Display
Fixed help label rendering issues in the Settings UI.

## ♻️ Refactoring

- Cleaned up trailing whitespace and formatting in `esphome.py` (Ruff compliance)
- Shared `RangeSlider` component for both cover position/tilt and output brightness/duration
- Improved ESPHome remote device Settings UI with entity discovery workflow
- AI wizard prompt improvements for input configuration

## 📦 Files Changed (highlights)

| Area | Key Files |
|------|-----------|
| Remote Outputs | `boneio/components/output/remote.py`, `boneio/schema/remote_outputs.yaml` |
| ESPHome Integration | `boneio/core/remote/esphome.py` |
| Remote Inputs | `boneio/components/input/remote/base.py`, `boneio/core/manager/inputs.py` |
| WebSocket Sync | `frontend/src/App.tsx`, `frontend/src/hooks/useWebSocket.ts` |
| Slider Animation | `frontend/src/components/RangeSlider.tsx` |
| MQTT Discovery | `frontend/src/components/UISettings/tables/RemoteDeviceTable.tsx` |
| Alarm Integration | `boneio/core/manager/manager.py` |
