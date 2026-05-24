# Changelog

All notable changes to boneIO Black are documented in this file.

---

## v1.4.0dev8 (2026-05-24)

### ✨ New Features

- **HA Dashboard — reorganized layout** — Dashboard is now organized into clear sections: "Podlewanie ręczne" (valve tiles in rows of 2), "Czasy podlewania" (zone durations as compact inline entities card), "Ustawienia", "Sterowanie", "Harmonogramy", "Sensory", "Zdarzenia".
- **Dynamic duration max** — Zone duration number entity max is now based on configured duration + 20 min (clamped to [30, 120]) instead of hardcoded 1440 min. Prevents accidental 24-hour irrigation.
- **Modbus device: EHT-TOPVENTIL-PLUS** — Added `eht-topventil-plus` to the allowed modbus devices list in schema.

### 🐛 Bug Fixes

- **Compact action buttons** — Replaced bulky `button` cards (Pause/Resume/Next) with compact `entities` card rendering them as single-line rows.
- **Duration input style** — Changed numeric-input from full-width `slider` to compact `+/-` `buttons` mode.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev7...v1.4.0dev8

---

## v1.4.0dev7 (2026-05-24)

### ✨ New Features

- **Next Run Time sensor** — New `device_class=timestamp` sensor for irrigation controllers that shows when the next scheduled run will occur (e.g. "in 19 hours"). Uses `mdi:calendar-clock` icon. Updates on schedule/skip/standby changes.
- **HA Dashboard YAML generator** — New `/api/irrigation/dashboard?ctrl_id=` endpoint generates complete HA Lovelace dashboard YAML for irrigation controllers. Includes: heading with badges, settings entities, action buttons, sensor tiles (zone end time, next run), zone tiles with duration sliders, schedule skip switches, and event entity.
- **Dashboard export button** — Per-row `FaFileExport` button in TemplateTable for irrigation items. Copies the generated HA dashboard YAML to clipboard for the specific controller.
- **Suggested area in HA discovery** — Irrigation controllers now include `suggested_area` in their HA MQTT discovery device metadata, allowing Home Assistant to auto-assign entities to the correct area.

### ♻️ Refactoring

- **Reusable dashboard card builders** — Extracted generic HA card primitives (`heading_card`, `tile_card`, `entities_card`, `button_card`, `entity_badge`, `horizontal_stack`, `sensor_tile`, `slider_tile`, `cards_to_yaml`) into `boneio/webui/dashboard_cards.py`. Reusable for future cover/light/alarm dashboard generators.
- **`build_entity_id` with configurable prefix** — Entity ID builder now accepts a domain prefix parameter (`irrigation`, `cover`, etc.) instead of hardcoded `irrigation`.
- **`ha_irrigation_timestamp_sensor_message` icon param** — Added optional `icon` parameter with `mdi:timer-sand` default, allowing custom icons per sensor type.
- **TableActions / MobileCard** — Extended with optional `onDashboard` callback; renders `FaFileExport` icon between Duplicate and Delete buttons.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev6...v1.4.0dev7

---

## v1.4.0dev6 (2026-05-24)

### ✨ New Features

- **Irrigation zones — collapsible accordion** — Zones are now displayed as collapsible accordions with a compact summary (name, valve, duration, frequency, enabled status). New zones auto-expand for editing; existing zones are collapsed by default for better overview.
- **Irrigation zones — reorder** — Added ▲/▼ buttons to move zones up/down in the list. Zone order determines irrigation sequence.
- **Irrigation zones — add button at bottom** — "Add zone" button is now shown both at the top and bottom of the zone list to avoid scrolling.
- **Template duplication** — New 📋 (copy) button in template table. Deep-clones the template with `_copy` suffix on IDs and `(copy)` suffix on names. Opens as a new item for editing. Irrigation zone IDs are also adjusted to avoid conflicts.
- **Platform icons** — Added dedicated emoji icons for irrigation (💧) and gate/cover (🚪) templates in the table view.

### 🐛 Bug Fixes

- **Irrigation AI prompt — light output filter** — AI prompt now explicitly forbids using "light" type outputs for irrigation valves and pumps.
- **AI context — output type awareness** — Added `output_type` ("light"/"switch") to each output in AI context. Prompt now guides AI to use appropriate action types per output type.
- **AI context — remote devices guidance** — Added instructions for `remote_output` and `remote_cover` actions with `remote_device`, `output_id`, and `cover_id` fields.
- **AI context — remote binary sensors** — Added `binary_sensors` from ESPHome devices to remote device context.
- **httpx test dependency** — Added `httpx>=0.28.0` to test dependencies (required by FastAPI's `TestClient`).

### ♻️ Refactoring

- **TableActions** — Extended with optional `onDuplicate` prop; renders copy icon between Edit and Delete.
- **MobileCard** — Added `onDuplicate` support for mobile template view.
- **TableRenderer** — Passes `onDuplicate` through to TemplateTable.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev5...v1.4.0dev6

---

## v1.4.0dev5 (2026-05-23)

### ✨ New Features

- **Reusable AI Assistant Shell** — Extracted `AiAssistantShell.tsx` component shared across all AI-assisted forms (EventForm, BinarySensorForm, RemoteInputForm, IrrigationForm). Single source of truth for the collapsible accordion UI, copy/paste buttons, paste dialog, and status alerts.
- **AI prompt — output type awareness** — The AI context now includes `output_type` ("light" or "switch") for each output. Prompts guide AI to use appropriate action types (e.g., BRIGHTNESS_UP for lights, TOGGLE/ON/OFF for switches).
- **AI prompt — remote devices guidance** — Added instructions for using `remote_output` and `remote_cover` action types with proper `remote_device`, `output_id`, and `cover_id` fields.
- **AI prompt — remote binary sensors** — Added `binary_sensors` to remote device context so AI can see available remote inputs from ESPHome devices.
- **Irrigation AI — switch-only rule** — Irrigation prompt now explicitly forbids using "light" type outputs for valves and pumps.

### 🐛 Bug Fixes

- **AI Config — missing remote inputs** — `buildAiConfigContext` now includes `binary_sensors` for each remote device (merged from `binary_sensors` + `_discovered_binary_sensors`), fixing empty remote input list in AI prompt.
- **httpx test dependency** — Added `httpx>=0.28.0` to `[tool.pdm.dev-dependencies] test` — required by FastAPI's `TestClient` which is used in `test_irrigation_ai.py`.
- **LoxUDP protocol fixes** — Fixed LoxUDP protocol communication issues.
- **Remote output interlock** — Fixed remote output interlock behavior.
- **Remote cover tilt action** — Fixed missing tilt action for remote covers.

### ♻️ Refactoring

- **AiConfigAssistant simplified** — Reduced from 239 to 146 lines by delegating UI to `AiAssistantShell`.
- **IrrigationForm AI cleanup** — Removed ~100 lines of duplicated AI UI code, replaced with `AiAssistantShell` component.
- **Nested accordion removed** — The "Szczegóły" (Details) inner accordion was removed from AI assistant since the whole block is already collapsible.
- **AI state management unified** — `IrrigationForm` now uses `aiStatus` object pattern (matching `AiConfigAssistant`) instead of separate `aiError`/`aiSuccess` states.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev4...v1.4.0dev5

---

## v1.4.0dev4 (2026-05-17)

### 🐛 Bug Fixes

- **Interlock Groups API — always returning empty** — The `/api/interlock-groups` endpoint referenced `manager._output_manager`, but the Manager class stores OutputManager as `manager.outputs`. The `hasattr()` check always failed, returning `{"groups": []}`. Fixed the attribute reference and added config-based scanning as fallback.
- **Remote Output Form — interlock groups not shown** — The frontend `ArrayTableWidget` only fetched interlock groups from the API for local outputs (`sectionType === 'output'`). Extended to also fetch for `remote_outputs`. Additionally, the widget now scans all output config data (`allOutputs` + current section items) for `interlock_group` values, merging them with the API response for resilience.

### ✨ Improvements

- **Interlock Groups API — config-based discovery** — The endpoint now also scans YAML configuration (`output` and `remote_outputs` sections) for interlock group names. This ensures groups are visible in the UI even before a config reload instantiates outputs at runtime.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev3...v1.4.0dev4

---

## v1.4.0dev3 (2026-05-17)

### ✨ New Features

- **Venetian Cover Tilt Restore** — New `tilt_restore_after_close` option automatically restores the previous tilt angle after the blinds finish moving to an intermediate position. Skipped at extremes (0% fully closed, 100% fully open). Works with both `close()` and `set_cover_position()`. Configurable via WebUI (venetian platform only).
- **Irrigation — Sequential Water Source Activation** — Water sources with multiple outputs now support configurable delay between activations (`output_start_delay_s`). Outputs activate in order and deactivate in reverse.
- **Irrigation — Interlock-Aware Activation** — If an output is blocked by an interlock during water source activation, already-activated outputs are rolled back and a fault notification is sent.

### 🐛 Bug Fixes

- **Type safety in `_execute_single_action`** — Consolidated duplicate `None` guards for entity IDs and action names into a shared validation block at the top of the method, fixing 5 Pyright `reportArgumentType` errors.
- **Import path for `BasicOutput`** — Fixed wrong import in `water_source.py` (`boneio.components.template` → `boneio.components.output.basic`).
- **`BasicOutput` type annotation** — Fixed `interlock_groups: list[str] = None` to `list[str] | None = None`.
- **Binary sensor device class** — Added `sound` to `BinarySensorDeviceClass` type.
- **Blueprint picker UX** — Made button more descriptive and added cursor-pointer hover state.
- **Mobile type switcher** — Fixed buttons overlapping hint text on small screens.

### ♻️ Refactoring

- **Delay & cancel action system** — Added comprehensive test suite for delayed/cancellable actions.
- **Remote output improvements** — Remote outputs now show proper ID and 'Remote' badge in dropdowns; included in `allOutputs` for irrigation and other forms.
- **i18n** — Translated all hardcoded strings in `OutputSelectDropdown`.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev2...v1.4.0dev3

---

## v1.4.0dev2 (2026-05-15)

### 🐛 Bug Fixes

- **Cover Relay Dropdown — "No outputs available" after saving** — Cover form filter now accepts outputs with `output_type` of `cover`, `none`, or missing (race condition during config reload could cause `output_type` to be absent, making the dropdown empty).

### ✨ Improvements

- **Sidebar section grouping** — Remote sections (Remote Devices, Remote Inputs, Remote Outputs) are now visually grouped in a blue-tinted frame labeled "External Devices". Restart-required sections are similarly grouped in a warning-tinted frame labeled "Sections requiring restart".

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev1...v1.4.0dev2

---

## v1.4.0dev1 (2026-05-15)

### ✨ New Features

- **Remote Outputs (`remote_outputs` section)** — Register switches and lights from remote ESPHome/MQTT devices as first-class outputs in boneIO. Outputs appear in the WebUI with full ON/OFF/TOGGLE control and area assignment.
- **Brightness Control for Remote ESPHome Lights** — If an ESPHome light supports brightness, the remote output gains a brightness slider in the WebUI. Includes real-time synchronization with Home Assistant, smooth animated slider transitions (ease-out cubic, 250ms), and debounced API calls with 800ms cooldown.
- **Remote Binary Sensors (ESPHome)** — Subscribe to binary sensors on ESPHome devices and use them as triggers for boneIO actions. Only sensors with registered callbacks are logged.
- **Remote Inputs Refactor** — Unified local and remote input handling with consistent state management. Remote devices can now trigger alarm panel actions.
- **WLED Brightness Support** — Merged PR #65 — WLED devices now support brightness control via the remote device API.
- **OLED Display Improvements** — Added OLED display tests, fixed sleep behavior on single click, cover change settings via OLED display.
- **Modbus Device Temporary Disable** — Temporarily turn off a single Modbus device without removing its configuration.

### 🐛 Bug Fixes

- **Frontend — Brightness State Not Updating** — WebSocket output deduplication compared only `state` and `name`, ignoring `brightness`. Changes on a light already ON were silently discarded.
- **Frontend — MQTT Discovery Shows 0 Outputs/Covers** — Backend nests outputs/covers under `mqtt` key in `to_dict()`, but frontend read top-level fields.
- **Frontend — Slider Jump-Back on Brightness Change** — Slider briefly jumped back to the old value due to stale ESPHome callbacks being processed before the new state arrived.
- **Backend — Entity Type Routing in ESPHome** — `control_output()` always delegated to `control_switch()`, failing for light entities. Now auto-detects entity type.
- **Backend — Connect Before Entity Lookup** — `control_switch()` and `control_light()` looked up entity keys before `connect()`. If entities hadn't been populated yet, commands silently failed.
- **Backend — Remote Output Lazy Resolution** — `register_remote_outputs()` was called during `Manager.__init__()` before device connections were established, causing all remote outputs to be skipped.
- **Input Selection — Case Sensitivity** — Fixed inputs not appearing in selection dropdown when named with capital letters.
- **Help Label Display** — Fixed help label rendering issues in the Settings UI.

### ♻️ Refactoring

- Cleaned up trailing whitespace and formatting in `esphome.py` (Ruff compliance)
- Shared `RangeSlider` component for both cover position/tilt and output brightness/duration
- Improved ESPHome remote device Settings UI with entity discovery workflow
- AI wizard prompt improvements for input configuration

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.3.1...v1.4.0dev1

---

## v1.3.1 (2026-05-07)

Maintenance release focused on stability, type safety, and Home Assistant integration improvements.

### ✨ New Features

- 🔧 **Support for legacy 0.2 / 0.3 boards** — added device definitions for older boneIO Black hardware revisions
- 🏠 **HA Update entity changed to binary sensor** — firmware update entity is now a binary sensor for cleaner HA integration

### 🐛 Bug Fixes

- **Cover position precision** — fixed inconsistent float/int conversion in cover position calculations, eliminating rounding drift during movement
- **Cover timestamp tracking** — fixed incorrect timestamps in cover state updates
- **HA discovery device_class** — fixed null device_class in Home Assistant autodiscovery by storing it directly on the input object
- **HA Update entity state during firmware restart** — update entity now correctly shows 'Updating' state during firmware restart instead of going offline
- **Event form click handling** — fixed click event handling in the WebUI event configuration form

### ♻️ Refactoring

- **Unified device_class** — refactored device_class to be a single source of truth on the input object (GpioBaseClass)
- **Removed gpio_mode** — deprecated gpio_mode setting, now handled by kernel overlay
- **Removed CAN System settings** — CAN configuration migrated to system migrations, manual settings no longer needed
- **Type safety improvements** — fixed multiple type checker issues across the codebase (Pyrefly/Pyright compatibility)

### ⚠️ Duplicate Entity Fix in Home Assistant

If you see **duplicated entities** for your boneIO Black device in Home Assistant after updating:

1. Go to Home Assistant → **Settings** → **Devices & Services** → **Devices** tab
2. Enter **Selection Mode**, select the boneIO Black devices with duplicated entities, and **delete** them
3. Open the boneIO controller's WebUI → **Settings** → **Communication Protocols** → **MQTT** tab
4. Click **"Delete and resend HA Discovery"**

This will cleanly re-register all entities without duplicates.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.3.0...v1.3.1

---

## v1.3.0 (2026-04-21)

Spring release — packed with new features, protocol support, and a complete WebUI overhaul!

### ✨ New Features

- 🌿 **Multi-zone irrigation controller** — schedules, per-zone intervals, water source management, master valve support, and a full dashboard UI with real-time zone countdown. All controlled also from Home Assistant!
- 🎛️ **Conditional actions** — time ranges, date ranges, and entity state conditions with AND/OR logic. Actions fire only when conditions are met
- 🎛️ **Each output now has individual action capabilities** — fine-grained control over what each output can do
- 📊 **Live graphs** added to the WebUI dashboard for real-time data visualization
- 📊 **Simple history view** for sensors — see past values at a glance
- ⏱️ **Timed output with HA input** — change the timer value directly from Home Assistant, no YAML restart needed
- 🔌 **LoxUDP protocol** — initial integration for Lox UDP communication
- 🔌 **CANOpen protocol** — initial support for CAN bus industrial devices
- 🏠 **Experimental `ha_child_devices` mode** for HA discovery — organize entities as child devices
- 🏠 **Output groups visible in HA** — output groups are now exposed to Home Assistant with their member outputs, so you can see which outputs belong to each group
- 🏠 **Entity category reorganization** — entities moved into proper HA categories (diagnostic, config) for a cleaner HA UI
- 🏠 **Republish states on MQTT autodiscovery resend** — ensures HA always has the latest state after reconnects
- 🔧 **48×4A legacy board support** — added device type for older 48-output / 4A boards
- 🔧 **Tilt support for remote devices** — venetian blinds on remote boneIO devices now support tilt actions
- 📦 **Modbus entity naming** — custom entity names for Modbus devices
- 📦 **Temperature sensor rounding** — configurable decimal rounding for temperature readings
- 📦 **Serial number in backup filenames** — easier identification of backup files across multiple devices

### 🐛 Bug Fixes

- **OLED refresh interval** — fixed display refresh timing causing stale or flickering content
- **Modbus WebUI loading time** — significantly reduced initial load time of Modbus device view
- **Modbus communication isolation** — other Modbus traffic is now blocked while using WebUI tools, preventing bus conflicts

### ♻️ UI / UX Improvements

- **Hundreds of UI fixes** across the entire WebUI — padding consistency, card styling, shadow standardization, responsive layout improvements
- **System Settings overhaul** — redesigned Current Version, Available Versions, App Permissions, CAN Permissions, and Migrations sections
- **Migrations table** — professional table layout with descriptions, status badges, and GitHub source links

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.2.0...v1.3.0
