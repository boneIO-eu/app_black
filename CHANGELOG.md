# Changelog

All notable changes to boneIO Black are documented in this file.

---

## v1.5.0dev13 (2026-07-18)

### 🐛 Bug Fixes

- **Config save timeout on large WLED configs** — Users with 7+ WLED devices experienced Axios 5s timeout when saving config. The 219 effects + 72 palettes per device created ~64KB of YAML data. Root causes:
  - **`run_in_executor`** — `update_config_section()` (synchronous YAML I/O) now runs in a thread pool instead of blocking the async event loop.
  - **Frontend timeout** — Config save timeout increased from 5s to 15s for large payloads.

### ♻️ Refactoring

- **WLED effects/palettes → JSON cache** — WLED effects, palettes, and segments (device firmware metadata) are now stored in `.wled_cache.json` instead of `config.yaml`. This reduces config size by 99% (64KB → 833 bytes) and eliminates YAML serialization bottleneck on ARM.
  - **Config migration v4** — Existing configs are automatically migrated: effects/palettes/segments are extracted to `.wled_cache.json` and stripped from YAML.
  - **Auto-populate** — Cache is automatically populated from WLED `/json` API on device connect.
  - **New API** — `GET /api/remote-devices/{id}/wled_info` and `GET /api/remote-devices/wled_info` serve cached metadata to frontend.
  - **Defense in depth** — `update_config_section()` strips WLED metadata from `remote_devices` before saving, even if frontend sends it back.
  - **Not in backup** — Cache auto-regenerates from WLED API, not included in config backups.
  - **Schema updated** — `effects`, `palettes`, `segments` removed from `remote_devices.yaml` schema.

---

## v1.5.0dev12 (2026-07-18)

### 🐛 Bug Fixes

- **WLED `.local` DNS resolution** — Force `ThreadedResolver` (system NSS/Avahi) instead of aiohttp's default `AsyncResolver` (c-ares) which cannot resolve mDNS `.local` hostnames. This caused `Name or service not known` errors even though `ping` worked fine from the same host.
- **WLED blocking all inputs** — WLED HTTP requests (with up to 10s DNS timeout) were blocking the EventBus worker, freezing ALL input events until the request completed. Now uses fire-and-forget pattern (`asyncio.create_task`) so WLED failures don't affect other inputs.
- **WLED timeout reduced** — HTTP timeout reduced from 10s to 3s total / 2s connect for faster failure detection.
- **Gate cover opening on restart** — Binary sensor `initial_send` events were routed through EventBus to gate covers, causing HA automations to trigger on every restart. Gate covers now read sensor state silently via `sync_initial_state()` during startup instead of relying on EventBus events. `publish_only` events are blocked from template routing.

---

## v1.5.0dev9 (2026-07-17)

Major UI overhaul for mobile, new configuration tools (Teach Mode, Binding Matrix, Quick Actions), serial number override for RMA exchanges, and significant performance improvements.

### ✨ New Features

- **Quick Action Sheet (Phase 2)** — Long-press any input to open a bottom sheet for one-tap output toggling. Supports remote outputs and covers. On mobile, dialogs render as native bottom sheets with swipe-to-dismiss.
- **Teach Mode (Phase 3)** — Batch input→output linking tool with area filters, auto-ignore for sensors, manual ignore picker, category tabs, bindings viewer, and a Test (Play) button. Responsive: modal on desktop, full-screen on mobile.
- **Binding Matrix** — New settings section showing all input→output bindings in a grid. Clickable cells open inline edit dialogs, drag-to-scroll on large matrices, pencil icon for editing, and full i18n support.
- **Serial Number Override (Backup/Restore)** — When restoring a backup from a different controller, the system detects serial mismatches and offers to adopt the old controller's identity. Preserves MQTT topics, HA entity IDs, and dashboard mappings across RMA exchanges. Manual override with real-time regex validation in boneIO settings.
- **OLED Extra Sensors Auto-Detection** — Extra screen sensors form now fetches available modbus coordinators and dallas sensors from `/api/sensors/screen_available` and presents dynamic select dropdowns instead of error-prone text inputs.
- **Optimized Startup (`/api/init`)** — Unified endpoint bundles version, serial, auth, PWA, and cloud data into a single HTTP request, eliminating 5 duplicate requests on page load.
- **Reusable Entity Components** — `EntityCard`, `EntityGrid`, `SearchableMultiEntityPicker`, `SettingsToggleGroup`, and `BottomPeekBar` components consolidate card styles, hover actions, and responsive layouts across all views.
- **NumericInput Component** — All `type="number"` inputs migrated to a dedicated component with select-all-on-focus for better mobile UX.

### ⚡ Performance

- **Fast Config Reload** — Skip Cerberus schema validation during reload, reducing config reload time from ~20s to ~1s.

### 🐛 Bug Fixes

- **WebSocket Race Condition** — Resolved race condition causing empty views on initial page load.
- **Quick Action Lookup** — Case-insensitive name matching and `boneio_input` parameter support when registering inputs.
- **HA Discovery Re-send** — Include `device_class` when re-sending discovery messages during reload.
- **Binding Matrix** — Fixed duplicate React keys, text selection interference, and drag-to-scroll only activating when mouse is held.

### ♻️ Improvements

- **Mobile UI Overhaul** — Dialogs and select menus render as bottom sheets on mobile with slide animations. Adjusted container padding, button/input sizing for touch.
- **Removed `serial_no` alias** — Deprecated `serial_no` property removed from `ConfigHelper`; all code uses `serial_number`.
- **Navigation label** — Serial override label changed from `(override: X)` to `(as: X)`.
- **Modbus Device Defaults** — Default update interval for `boneio-edge-temp` sensors set to 30s.

---

## v1.5.0dev8 (2026-07-17)

Consolidation of startup API requests, UI styling upgrades, reusable layout components, and configuration search improvements.

### ✨ New Features

- **Optimized Startup (/api/init)** — Added a unified `/api/init` endpoint and React `AppInitContext` to bundle startup data (version, serial number, authentication status, PWA config, and cloud registration info) into a single HTTP request, eliminating 5 duplicate requests on page load.
- **Reusable Entity Components** — Introduced `EntityCard` and `EntityGrid` components to consolidate and standardize card styles, hover actions, locking/interlocks, and responsive layouts across `InputsView`, `OutputsView`, and `ModbusView`. Removed the deprecated and duplicate `OutputItem` component.
- **Reusable Settings Widgets** — Added `SearchableMultiEntityPicker` (for multi-selection area dialogs), `SettingsToggleGroup` (for HA/iOS-style grouped toggle settings), and `BottomPeekBar` (reusable mobile bottom sheet component with swipe-to-expand gesture).

### 🐛 Bug Fixes

- **Quick Action Lookup** — Supported case-insensitive name comparisons and matching against the `boneio_input` parameter when registering or identifying inputs for quick actions.

### ♻️ Improvements

- **Mobile View & Transitions** — Added smooth slide animations for mobile dialog overlays and select menus via BaseUI attributes, adjusted container padding, and improved mobile button/input styling.
- **Modbus Device Defaults** — Updated default update interval for `boneio-edge-temp` sensors to 30s.

---

## v1.5.0dev5 (2026-06-25)

Critical crash loop fix — application restarted indefinitely (restart counter 87+) on devices with Modbus text sensors (e.g., EHT Topventil Plus).

### 🐛 Bug Fixes

- **ModbusDerivedTextSensor crash loop** — `discovery_message` was decorated with `@property` instead of being a regular method. `BaseEntity.send_ha_discovery()` calls `self.discovery_message()` with parentheses — the property returned a `dict`, then `dict()` raised `TypeError: 'dict' object is not callable`. This crashed the Modbus coordinator task inside `asyncio.gather(FIRST_COMPLETED)`, causing immediate application shutdown and infinite restart loop. Removed the `@property` decorator to make it a regular method, consistent with all other entity classes.
- **Python 3.13 executor shutdown RuntimeError** — `StateManager.save_state()` was scheduled via `call_later(1, ...)` timer handles that survive `_cancel_all_tasks()` during shutdown. When the timer fired after `shutdown_default_executor()`, `run_in_executor(None, ...)` raised `RuntimeError: Executor shutdown has been called` (new check in Python 3.13). Added `_shutting_down` flag, `try/except RuntimeError` fallback to synchronous write, and new `cancel_pending_and_save()` method for explicit cleanup.
- **Output relay executor guard** — `BasicOutput.async_turn_on()` and `async_turn_off()` now catch `RuntimeError` from executor shutdown and fall back to synchronous `turn_on()`/`turn_off()` during application exit.

### ♻️ Improvements

- **Graceful shutdown ordering** — `runner.py` cleanup now calls `state_manager.cancel_pending_and_save()` before `event_bus.stop()` to prevent new state saves from being scheduled during shutdown.
- **Modbus wizard dialog scrollable** — `AddModbusDeviceWizard` dialog is now scrollable (`max-h-[85vh] overflow-y-auto`) with tighter padding for better UX on smaller screens.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.5.0dev4...v1.5.0dev5

---

## v1.5.0dev3 (2026-06-17)

Critical irrigation schedule fix — schedule tasks were permanently killed after the first cycle completed.

### 🐛 Bug Fixes

- **Irrigation schedule dies after first cycle** — `shutdown()` called `stop_schedules()` which cancelled the `asyncio.Task` running `_run_schedule_loop()`. When a scheduled cycle completed normally (`_advance_to_next_zone` → `shutdown`), the schedule task was killed permanently — the next day's schedule would never fire, with zero log output. Split into `shutdown()` (stops active cycle only, safe to call from schedule tasks) and `full_stop()` (stops cycle + cancels schedule tasks, used by IrrigationManager for teardown/reload).
- **Cover state not retained on MQTT broker restart** — `send_state()` in `BaseCover` published state and position without `retain=True`. After an MQTT broker restart, HA would show covers as "unavailable" until the next state change. Added `retain=True` to both state and position MQTT publishes.

### ✨ Improvements

- **Resend all entity states on MQTT reconnect** — New `_resend_all_states()` method in Manager publishes current state of all outputs and covers after MQTT reconnect, ensuring HA always has correct state after a broker restart.

### 🧪 Tests

- 4 new regression tests in `TestScheduleSurvival` — verify `shutdown()` preserves schedule tasks, `full_stop()` cancels them, cycle completion preserves schedule, and `start_full_cycle()` while running preserves schedule.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.5.0dev2...v1.5.0dev3

---

## v1.5.0dev2 (2026-06-13)

Critical irrigation fix — schedule tasks were never started after v1.5.0dev1.

### 🐛 Bug Fixes

- **Irrigation schedules not starting** — Commit `c8a0841` ("fix irrigation scheduler") split `IrrigationManager.start()` into `start()` (with schedule tasks) and `reconnect()` (without schedule tasks) to prevent resetting timers on MQTT reconnect. However, `reconnect_callback()` — the only entry point for both first connection and reconnections — was changed to call `reconnect()` instead of `start()`. This meant `start_schedules()` was **never called**, silently disabling all irrigation schedules. Fixed by detecting first connection (no running schedule tasks) in `reconnect()` and starting schedules automatically.
- **PWA build failure** — Monaco editor TS worker grew to 6.9 MB after dependency updates, exceeding the 5 MB workbox precache limit. Excluded worker chunks from precache (they're loaded on-demand) and added runtime `CacheFirst` strategy for workers instead.

### 📦 Other Changes

- **Frontend dependency updates** — Bumped React 19.2.7, Vite 8.0.16, Tailwind 4.3.0, DaisyUI 5.5.23, ESLint 10.x, and other dependencies.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.5.0dev1...v1.5.0dev2

---

## v1.5.0dev1 (2026-06-08)

HA Dashboard export wizard, LoxUDP improvements, disk sensor discovery, WLED remote outputs, and various fixes.

### ✨ New Features

- **HA Dashboard Export Wizard** — New multi-step wizard in the Tools tab for generating Home Assistant Lovelace dashboard YAML sections. Supports outputs (lights, switches, valves), covers, output groups, irrigation, alarm panels, gate covers, and Modbus devices. Per-entity selection with localStorage persistence, per-area YAML copy buttons, and entity count statistics per area.
- **WLED Remote Output support** — Added support for WLED devices as remote outputs with brightness control.
- **All disk sensors** — Disk sensor discovery now finds all mounted partitions, not just the root filesystem.
- **OLED FIFO permissions migration** — New migration `v1_5_0_fix_oled_fifo_permissions` ensures correct permissions on OLED message FIFO.

### 🐛 Bug Fixes

- **Irrigation scheduler** — Fixed scheduler timing issues causing missed or delayed zone activations.
- **LoxUDP protocol** — Improved reliability of Lox UDP communication with better keepalive handling, reconnection logic, and binary value encoding.
- **Docker ghost dirs in boneio-migrate** — `install_file` now tolerates Docker overlay filesystem ghost directories during migration.
- **HA entity slugify** — `_ha_slugify()` now collapses multiple consecutive underscores into a single one, matching Home Assistant behavior for entities with stripped non-ASCII characters.

### ♻️ Refactoring

- **TemplateManager property rename** — Renamed sub-manager accessors from `alarms`/`gates`/`thermostats` to `alarm_manager`/`gate_manager`/`thermostat_manager` to clarify they return manager objects, not entity lists.
- **Dashboard card builders** — Extended `dashboard_cards.py` with generators for alarm, gate, cover, and Modbus tile cards.
- **LogViewer improvements** — Enhanced log viewer UI with better filtering and display.
- **Output table HA entity preview** — Output table now shows HA entity ID preview for each output.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.4dev1...v1.5.0dev1

---


## v1.4.3 (2026-06-04)

Migration helper fixes and OLED shutdown UX improvements.

### 🐛 Bug Fixes

- **boneio-migrate helper** — `systemctl reload/restart` actions now tolerate inactive services instead of failing the entire migration. Fixes image build failures when mosquitto was stopped during `setup_boneio.sh`.

### ✨ New Features

- **OLED late-shutdown service** — New `boneio-oled-shutdown.service` displays "System stopped. Safe to unplug." on the OLED **after** the network is down during shutdown.
- **Restart-aware ExecStopPost** — `boneio.service` only shows "Shutting down..." during actual system shutdown, not during `systemctl restart boneio`.

### 📦 Migration: v1.4.3

- Installs `boneio-oled-shutdown.service` (late-phase shutdown OLED message)
- Updates `boneio.service` with shutdown-aware `ExecStopPost`

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.2...v1.4.3

---

## v1.4.2 (2026-06-03)

Hotfix — TimePeriod object handling in input forms.

### 🐛 Bug Fixes

- **EventForm crash** — `parseMs()` called `.match()` on TimePeriod objects (`{milliseconds: 220}`) instead of strings, causing `Uncaught TypeError: val.match is not a function`. Replaced with the existing `convertTimeperiodToMilliseconds()` utility.
- **BinarySensorForm wrong bounce_time** — `typeof data.bounce_time === 'number'` always returned `false` for TimePeriod objects, displaying default `120ms` instead of the configured value. Fixed using `convertTimeperiodToMilliseconds()`.

### 🛡️ Improvements

- **Pre-commit hook** — Added `tsc --noEmit` TypeScript type-check before vitest to catch build-breaking issues (unused variables, type errors) before commit.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.1...v1.4.2

---

## v1.4.1 (2026-06-03)

Hotfix release with SSL certificate renewal and Modbus chart improvements.

### 🐛 Bug Fixes

- **SSL certificate renewal** — `_cert_needs_refresh()` was checking file modification time (`st_mtime`) instead of the actual X.509 expiry date. If the cert file was touched by backup/copy/rsync, `mtime` would reset and the certificate would never be renewed even after expiry. Now parses the real `Not After` date using `openssl x509` and refreshes when the cert expires within 14 days.
- **Modbus sparkline charts for energy meters** — `shouldRenderHistory()` only whitelisted temperature/humidity sensors (by name pattern or unit `%`, `°C`, `rh%`). Energy meters with units like `W`, `kWh`, `V`, `A`, `Hz`, `VA`, `var` were excluded. Changed to show charts for all numeric read-only sensors that have a unit of measurement.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0...v1.4.1

---

## v1.4.0 (2026-06-03)

Major release — remote device support, irrigation overhaul, AI-assisted configuration, system monitoring, and dozens of bug fixes.

---

### 🔌 Remote Devices

- **Remote Outputs (`remote_outputs`)** — register switches and lights from remote ESPHome/MQTT devices as first-class outputs with ON/OFF/TOGGLE, area assignment, and interlock groups.
- **Brightness control** — remote ESPHome lights get a real-time brightness slider with smooth animations and debounced API calls.
- **Remote Binary Sensors** — subscribe to binary sensors on ESPHome devices for use as action triggers.
- **WLED brightness support** — WLED devices support brightness via the remote device API.
- **Remote cover tilt** — tilt actions for venetian blinds on remote boneIO devices.

---

### 🌿 Irrigation

- **Multi-zone irrigation controller** — schedules, per-zone intervals (`run_every_n`), water source management, master valve/pump support, and a full dashboard UI with real-time zone countdown.
- **Sequential water source activation** — water sources with multiple outputs activate in order with configurable delays (`output_start_delay`, `output_stop_delay`). Deactivation in reverse order.
- **Interlock-aware activation** — if an output is blocked by an interlock during water source activation, already-activated outputs are rolled back and a fault notification is sent.
- **Zone enabled toggle** — each zone can be individually enabled/disabled. Reflected in HA dashboard.
- **Zone `run_every_n` skip counter** — zones with `run_every_n > 1` correctly track their skip counters across multi-cycle runs. `next_run_iso`, `next_run_pretty`, `skip_count` published as valve entity attributes in HA.
- **Next Run Time sensor** — `device_class=timestamp` sensor showing when the next scheduled run will occur (e.g. "in 19 hours").
- **HA Dashboard YAML generator** — one-click export of a complete Lovelace dashboard per controller, with zones, durations, schedules, and controls.
- **Irrigation AI assistant** — AI-powered configuration wizard for creating irrigation setups from natural language descriptions.
- **Schedule timezone fix** — schedule times are now treated as local time instead of UTC.
- **Dynamic duration max** — zone duration max is based on configured duration + 20 min (clamped to [30, 120]) instead of hardcoded 1440 min.
- **Single-zone optimization** — controllers with 1 zone skip unnecessary `auto_advance`, `reverse`, and `next_valve` entities.
- **Manual start responsiveness** — clicking "Start" responds instantly; pump/valve delays no longer block the UI.

---

### 📊 System Monitoring

- **System sensors (CPU, Disk, Memory)** — percentage-based sensors with rich attributes:
  - Disk: `disk_total_gib`, `disk_used_gib`, `disk_free_gib`
  - Memory: `memory_total_gib`, `memory_used_gib`, `memory_available_gib`
- **Instant sensor values on UI load** — system sensors are included in WebSocket initial states, eliminating the 10-60s blank period after opening the UI.
- **Sensor attributes in UI** — GraphCard displays compact attribute chips (e.g. `Total: 28.65 GiB | Used: 2.28 GiB | Free: 25.19 GiB`) with dynamic unit extraction.
- **HA `json_attributes_topic`** — system sensors publish attributes as JSON, visible in HA's "More Info" dialog without extra entities.

---

### 🏠 Home Assistant Integration

- **`suggested_area` in HA discovery** — irrigation and other entities auto-assign to the correct area.
- **`json_attributes_topic`** — system sensors expose detailed metrics as HA entity attributes.
- **Entity category reorganization** — entities placed in proper HA categories (diagnostic, config).
- **Republish states on MQTT reconnect** — ensures HA always has the latest state.
- **Output groups in HA** — groups exposed with member outputs visible.
- **Remote output interlock** — interlock checks enforced for remote outputs and dimmer brightness.

---

### 🖥️ OLED Display

- **Screensaver timer reset** — screensaver countdown now resets from the last button press instead of the first.
- **Sleep behavior fix** — fixed single-click sleep toggle.

---

### 🎛️ Covers

- **Venetian tilt restore** — new `tilt_restore_after_close` option automatically restores the previous tilt angle after moving to an intermediate position. Skipped at extremes (0% / 100%).
- **Cover relay dropdown fix** — filter now accepts outputs with `output_type` of `cover`, `none`, or missing.
- **Cover position precision** — fixed float/int rounding drift during movement.

---

### 🤖 AI Configuration Assistant

- **Output type awareness** — AI correctly distinguishes between lights (brightness actions) and switches (toggle/on/off).
- **Remote device guidance** — AI knows about remote outputs, covers, and binary sensors.
- **Irrigation valve type filter** — AI explicitly avoids "light" type outputs for irrigation.

---

### 🧩 UI / UX Improvements

- **Input type change without restart** — switching between "Event Entity" and "Binary Sensor" takes effect immediately.
- **InputsView navigation fix** — long press on an input correctly navigates to its settings (not areas).
- **Clipboard in HA addon iframe** — fixed `navigator.clipboard.writeText()` in HA ingress iframe with `document.execCommand('copy')` fallback.
- **Sidebar section grouping** — remote and restart-required sections visually grouped.
- **Template duplication** — deep-clone templates with adjusted IDs.
- **Irrigation zones — collapsible accordion** with reorder buttons and add-at-bottom.
- **Live graphs** — sparkline charts in sensor/modbus views.
- **Modbus device temporary disable** — turn off a single Modbus device without removing config.

---

### 🐛 Bug Fixes

- **Irrigation `run_every_n` skip counter desync** — `_eligible_zones()` side effects caused counters to diverge. Split into pure filter + single-call counter update.
- **Config cache staleness** — `invalidate_config_cache()` now clears `ConfigHelper._config_cache`.
- **TimePeriod empty string crash** — frontend-sent `""` for optional TimePeriod fields no longer crashes Cerberus.
- **Remote output MQTT state** — remote outputs now publish state to MQTT (previously HA showed "unavailable").
- **Interlock bypass on dimmer brightness** — brightness changes now check interlock before allowing > 0.
- **ESPHome entity type routing** — `control_output()` auto-detects entity type instead of always delegating to `control_switch()`.
- **ESPHome connect-before-lookup** — entity commands no longer silently fail when entities haven't been populated.
- **Output group form ID** — form now uses correct `boneio_output` reference.
- **Interlock Groups API** — fixed always-returning-empty due to wrong attribute reference; added config-based fallback.
- **Frontend brightness deduplication** — WebSocket now considers `brightness` field in deduplication.
- **Frontend slider jump-back** — eliminated stale ESPHome callback processing.

---

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.3.1...v1.4.0

---

## v1.4.0dev14 (2026-06-02)

### 🐛 Bug Fixes

- **Clipboard not working in HA addon iframe** — `navigator.clipboard.writeText()` silently failed inside HA ingress iframe due to missing `allow="clipboard-write"` Permissions Policy. Added `iframe.allow = 'clipboard-read; clipboard-write'` to the addon dashboard iframe and created a reusable `copyToClipboard()` utility with `document.execCommand('copy')` fallback for HTTP contexts. Replaced all 10 occurrences across the frontend.
- **Irrigation manual start delay** — Clicking "Start" on a zone took 2-4 seconds to respond in the UI due to `valve_open_delay` and pump delays blocking the MQTT state publish. Added early `publish_all_states()` immediately after setting `RUNNING` state, before any hardware sleep delays.
- **Irrigation API response delay** — HTTP API endpoints for start/resume/next_valve blocked until all pump/valve delays completed. Changed to `asyncio.create_task()` fire-and-forget dispatch so the UI receives an instant response.
- **InputsView long press navigation** — Long press on an input item navigated to the wrong settings section (e.g. `/settings/event` instead of `/settings/local_inputs`).
- **Output group form ID** — Output group form used effective ID instead of `boneio_output`, causing mismatched entity references.

### ♻️ Refactoring

- **OLED screensaver timer** — Screensaver countdown now resets from the last button press instead of the first, improving UX.
- **Input type change** — Changing input type between "Event Entity" and "Binary Sensor" now takes effect immediately without requiring app restart.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev13...v1.4.0dev14

---

## v1.4.0dev13 (2026-05-28)

### 🐛 Bug Fixes

- **Critical: run_every_n skip counter desynchronization** — `_eligible_zones()` had side effects (incrementing skip counters) and was called multiple times per cycle (once at start + once per zone advance + once per repeat). This caused skip_count values to diverge across zones even when all had the same `run_every_n`. Fixed by splitting into pure `_eligible_zones()` (no side effects) and `_apply_skip_counters()` (called exactly once per scheduled cycle).

### ✨ New Features

- **Zone next_run as valve attributes** — Zones with `run_every_n > 1` now publish `next_run_iso`, `next_run_pretty`, `skip_count`, and `run_every_n` as JSON attributes on the valve entity. Visible in HA's "more info" dialog without extra sensor entities.
- **Zone enabled toggle in HA dashboard export** — Each zone valve tile now includes an inline "Enabled" switch in the exported HA dashboard YAML.
- **EHT Top Ventil config fix** — Modbus input configuration fix for EHT Top Ventil Plus (community contribution).

### 🧪 Tests

- 4 new regression tests for multi-cycle skip counter synchronization (9 zones × 8 cycles, mixed `run_every_n`, purity check).

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev12...v1.4.0dev13

---

## v1.4.0dev12 (2026-05-24)

### 🐛 Bug Fixes

- **Irrigation schedule timezone** — `_next_fire_time()` was treating user-configured schedule times (e.g. "18:00") as UTC instead of local time, causing schedules to fire 2h late in CEST and HA sensor to show wrong time. Now builds candidate in system local timezone and converts to UTC.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev11...v1.4.0dev12

---

## v1.4.0dev11 (2026-05-24)

### 🐛 Bug Fixes

- **Remote output MQTT state** — Remote outputs now publish their state to MQTT (`boneio/{serial}/output/{id}`). Previously HA showed them as "unavailable" because `_emit_state_event()` only emitted EventBus events for WebSocket, never MQTT.
- **Interlock bypass on dimmer brightness** — `async_set_brightness()` (remote) and `SET_BRIGHTNESS` MQTT handler (local) now check interlock before allowing brightness > 0. A dimmer slider could previously bypass an active interlock group.
- **TimePeriod empty string crash** — `strip_default_values()` / `clean_dict()` now skips empty strings and `None` values. Frontend could send `""` for optional TimePeriod fields (e.g. `output_start_delay`), causing Cerberus coercion error: `Unknown value ''`.
- **Config cache staleness** — `invalidate_config_cache()` now also clears `ConfigHelper._config_cache`, fixing stale schedule data after save.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev10...v1.4.0dev11

---

## v1.4.0dev10 (2026-05-24)

### ✨ New Features

- **Single-zone controller optimization** — Controllers with only 1 zone no longer create `auto_advance`, `reverse`, and `next_valve` entities (HA discovery, MQTT subscriptions, dashboard YAML). These are only meaningful for multi-zone controllers.

### 🐛 Bug Fixes

- **slider_tile inline layout** — Zone duration tiles now use `vertical: false`, `features_position: inline`, `style: slider` instead of `buttons`.
- **Valve tiles without horizontal-stack** — Each valve tile is a separate card (easier to edit manually in HA YAML editor).

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev9...v1.4.0dev10

---

## v1.4.0dev9 (2026-05-24)

### ✨ New Features

- **HA Dashboard — inline tile cards** — All settings, schedule skips, and controls now use compact `inline_tile` cards with `features_position: inline` and entity's HA friendly name (`name: {type: entity}`).
- **New reusable `inline_tile()`** — Generic dashboard card builder for compact inline tiles. Reusable for future dashboards (covers, gates, etc.).
- **Water source — tile card with select-options** — Water source select uses tile card with `features: [select-options]` and `features_position: inline`.
- **Sterowanie — horizontal tile cards** — Pause/Resume/Next valve rendered as tile cards in horizontal-stack instead of entities card.
- **Czasy podlewania — slider tile cards** — Zone duration tiles with `numeric-input` buttons, stacked vertically under a heading.
- **Podlewanie ręczne — valve tiles** — Zone valve tiles in rows of 2 for manual control.
- **Schedule skips folded into Ustawienia** — No separate "Harmonogramy" section; schedule skip switches appear as inline tiles in Ustawienia.

**Full Changelog**: https://github.com/boneIO-eu/app_black/compare/v1.4.0dev8...v1.4.0dev9

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
