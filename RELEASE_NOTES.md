# Changelog — v1.4.0

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
