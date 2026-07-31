# boneIO Black v1.5.0 — Release Notes

## 🎯 Highlights

- **WebUI performance overhaul** — startup from ~5 API requests down to 1, eliminated page reloads
- **Teach Mode** — batch input→output linking with area filters and diagnostics
- **Binding Matrix** — visual grid of all input-output bindings
- **Quick Action Sheet** — fast input→output linking from bottom sheet
- **Security hardening** — path traversal protection, CORS, auth improvements
- **40+ dev releases** tested in the field
- **Board v1.0 readiness** — software support for the upcoming hardware revision

---

## ✨ New Features

### 🎓 Teach Mode
- Batch input→output linking with visual entity picker
- Area filters, auto-ignore sensors, manual ignore picker
- Test (Play) button for instant action testing
- Category tabs and bindings viewer
- Premium responsive UI — modal on desktop, full-screen on mobile

### 📊 Binding Matrix
- Visual grid showing all input-output bindings at a glance
- Click cell to edit, inline edit dialog, drag-to-scroll
- Context menu filtered by input kind
- Section in Settings with proper sidebar navigation

### ⚡ Quick Action Sheet
- Bottom-sheet for fast input→output linking
- Support for remote outputs and covers
- Non-blocking saves with hot-reload

### 🚀 WebUI Performance
- Consolidated 5+ startup API calls into single `GET /api/init`
- Config cache with prefetch and generation-guarded invalidation
- Eliminated duplicate `GET /api/version`, `GET /api/name`, `GET /api/config` at startup
- Deferred Service Worker registration — no more competing with init requests
- Removed hard `window.location.reload()` on SW update
- Settings sidebar skeleton during config loading
- Keep-alive timeout 2→5s, manifest cache 5min
- Shallow compare prevents re-renders on periodic health checks

### 🌐 Remote Devices
- **WLED remote output support** — effects, palettes, segments from device cache
- **Remote binary sensor** in action conditions
- Separate "Remote Output" entity type in action conditions
- Remote inputs/outputs descriptions with action conditions info

### 📡 1-Wire Improvements
- Kernel-only 1-Wire operation (removed DS2482 userspace)
- Bus scan API and frontend "Scan 1-Wire Bus" button
- DS2482 1-Wire Expanders section in WebUI
- Migration v4 for ds2482/w1-therm transition

### 🔍 Other Features
- **MQTT Reference dialog** — show topics and payloads per entity
- **QDW90A liquid pressure sensor** added to Modbus device database
- **SearchableEntityPicker** — search, area grouping, recent items
- **NumericInput component** — replacing all type=number inputs
- **Serial number override** for backup/restore (RMA exchange)
- **OLED dynamic selects** for extra screen sensors
- **Node-RED backup** with SHA256 checksums and upload restore
- **Log Viewer** — groups repeating multi-line sequences
- **Overlay mismatch detection** when changing board version
- **Fast config reload** — skip Cerberus validation (~20s → ~1s)
- **Restart Application button** in System section

---

## 🔒 Security

- **Stage 1 hardening** — path traversal protection, CORS restrictions, auth improvements, security headers
- **Defense-in-depth** against sed injection in overlay operations
- **Rate limiting** sudo password attempts (3/5min per IP)
- **Overlay endpoint** proper HTTP status codes
- **CORS** — allow localhost dev servers only when `BONEIO_DEV` is set

---

## 🐛 Bug Fixes

- Fix WebSocket race condition causing empty views on initial load
- Fix irrigation interlock fault after water source change via HA select
- Fix crash loop on Modbus text sensors and Python 3.13 executor shutdown
- Fix WLED `.local` DNS resolution with ThreadedResolver
- Fix venetian tilt restore after opening movement
- Fix GPIO readback for missed RELEASE events (lower max_long_press to 30s)
- Fix config reload crash when YAML version is float (0.7 not '0.7')
- Fix duplicate React keys in BindingMatrix
- Fix long press on inputs page closing dialog on mouse release
- Fix Dallas sensor W1ThermSensor family prefix stripping
- Fix update progress not sent to HA (blocking subprocess → async)
- Fix migration skipping on fresh configs without legacy fields
- Fix binary sensor click in binding matrix opening correct tab
- Various i18n fixes (interpolation, missing keys, Polish translations)

---

## ♻️ Refactoring

- Split `config.py` into 5 logical modules
- Migrate all `type=number` inputs to `NumericInput` component
- Remove all `as any` casts from RemoteOutputForm
- Frontend refactored to reusable `EntityCard`, `EntityGrid`, and UI widgets
- ConfigContext reads from AppInitContext (no separate API call)

---

## 📦 Dependencies

- aiohttp 3.14.1, hypercorn 0.18.0, psutil 7.2.2

---

## ⬆️ Migration Notes

- **Config migrations v1–v5** run automatically on startup
- **OLED screens**: `ina219` → `ina` (auto-migrated)
- **1-Wire**: DS2482 userspace removed, kernel-only operation

---

## 🔮 Coming Next: Board v1.0

We are preparing for the release of **boneIO Black v1.0** — a new hardware revision with significant improvements. The software already includes full support, so upgrading to v1.5.0 now ensures a smooth transition when the new boards ship.

What's new in hardware v1.0:
- **DS2484 I2C-to-1Wire bridge** — reliable 1-Wire via I2C bus (replaces GPIO-based 1-Wire)
- **INA226 power monitor** — next-gen power measurement chip
- **Active-LOW MCP23017 relay boards** — new relay board design with cold-start safety, auto-detection, and state persistence
- **Unified OLED power screen** — auto-detects INA219 or INA226, no manual configuration needed

> Board v1.0 support is fully backward-compatible — existing boards continue to work as before.
