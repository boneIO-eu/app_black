# Work Log — BoneIO fork (M4rv-dev/app_black)

> **Read this first** when starting a new Claude Code session on this repo. It carries
> context that survives across sessions, model switches, and CLI restarts.

---

## Project overview

This is a **fork** of `boneIO-eu/app_black` maintained at `github.com/M4rv-dev/app_black`. The upstream
ships v1.4.0dev2; we extend it with the **expansion-board** feature (adding I²C MCP23017
expanders that double available outputs). The goal is to ship features upstream **doesn't have**,
while staying mergeable with their releases.

### Topology

| Remote | URL | Access |
|--------|-----|--------|
| `origin` | github.com/boneIO-eu/app_black | read-only (upstream) |
| `fork` | github.com/M4rv-dev/app_black | push (our fork) |

| Branch | Purpose |
|--------|---------|
| `dev-debian13` | Tracks upstream main; our base for merges |
| `feat/expansion-board` | Active feature branch (current) |

### Deployment

- **Target device**: BoneIO @ `192.168.1.22` (BeagleBone Debian 13, user `boneio`)
- **Deploy script**: `./deploy_backend.sh` (gitignored, contains password). Rsyncs the whole
  `boneio/` Python package to `/home/boneio/boneio/venv/lib/python3.13/site-packages/boneio/`,
  then restarts `boneio.service`.
- **Frontend**: Vite dev server at `localhost:5173` (proxies to device's API on `:8090` and
  Caddy/Node-RED on `:8091`). `.env.local` has `VITE_API_URL` + `VITE_NODERED_URL`.
- **Web UI on device**: direct Hypercorn on `:8090` OR via Caddy proxy on `:8091` (Caddy proxies
  BoneIO UI + provides Node-RED at `/nodered/`). For Node-RED tab to appear, use `:8091`.

---

## Architecture decisions

### Module pattern (CORE PRINCIPLE)

**BoneIO upstream is treated as core engine; our extensions live in dedicated `modules/` folders
with strict public APIs.** Touching upstream files is allowed only for 1 import + 1-2 use lines.

Why: BoneIO will keep releasing 1.4.x / 1.5; embedding logic in their files = merge conflicts
on every release. The module pattern keeps our merge surface minimal.

```
frontend/src/components/UISettings/modules/<feature>/
├── index.ts            ← public API — upstream imports only from here
├── components/         ← Presentational (sam render)
├── hooks/              ← stateful + side-effects + fetch
├── helpers/            ← pure functions
├── types/              ← TypeScript types
└── constants/

boneio/modules/<feature>/
├── __init__.py         ← public API
├── yaml_util.py        ← pure helpers
└── routes.py           ← endpoints + register_routes(app)
```

### Future re-skin (NOT in current scope)

A future project will provide an alternative UI as a **wrapper layer** over both boneIO
components AND our modules — written as additional modules, never modifying existing code.
Our modules MUST keep logic in hooks/helpers (not in components) so the re-skin can swap
components without touching logic.

### Memory & plans

- **Memory dir**: `~/.claude/projects/-Users-mariuszskupinski-Documents-BoneIO-app-black/memory/`
  (`MEMORY.md` index auto-loaded by Claude)
- **Active plan**: `~/.claude/plans/boardy-s-takie-jakie-starry-sun.md` (the modules refactor)

---

## Active scope

**Current task**: Refactor expansion-board feature into `modules/expander/` pattern.

**Why**: After merging upstream v1.4.0dev2 (commit `fbe2140`), audit revealed our code is scattered
across 7+ upstream files. Each future upstream release will conflict on the same spots. Module
pattern eliminates that.

**Phase status** (granular commits, easy to revert each):

| # | Phase | Status |
|---|-------|--------|
| 0a | Scaffold modules/expander/ + types + constants + index.ts | ✅ |
| 0b | Move expanderBoards + outputMcpUtils into module; add isExpanderOutput + getOutputStats; shim old paths | ✅ |
| 0c | Backend scaffold `boneio/modules/expander/` + yaml_util.py + routes.py + register in app.py | ✅ |
| A1 | Extract `useExpanderManager` + `<ExpanderManager />` from `BoneIOForm.tsx` | ✅ |
| A2 | Extract `useMcpHardware` + `<McpHardwareFields />` from `OutputForm.tsx` | ✅ |
| A3 | Extract `useOutputCapacity` + `<OutputAddButton />` from `ArrayTableWidget.tsx` | ✅ |
| A4 | Derive `outputKind` via `useOutputKind` (drop useState) | ✅ |
| B | Dedupe EX_ detection, MCP addresses, remove dead `onExpanderAdded` prop | ✅ |
| — | Verify (tsc + build + python smoke + anti-duplicate greps) | ✅ |
| — | Deploy + manual smoke test in UI | ✅ deployed; UI smoke test confirmed working by user |
| Future | Build/inject script POC (auto-apply modules onto fresh upstream) | 📋 idea, deferred |

---

## Timeline

### 2026-05-15 → 2026-05-16 — Session 1 (upstream merge + module refactor)

**Goal**: Catch up with upstream v1.4.0dev2 (was 14 commits behind), preserve our expansion-board
work, then refactor for future-merge friendliness.

**Done**:
- ✅ Configured git: `.gitignore` for `deploy_backend.sh` (password) + `.DS_Store`
- ✅ Created `feat/expansion-board` branch
- ✅ 5 thematic local commits before merge (backend split-write, BoneIO settings UI, OutputForm with
  TabsBox, UI polish, translations)
- ✅ Merged upstream `dev-debian13` → 6 manual conflict resolutions:
  - `ArrayTableWidget.tsx` — kept upstream's `FormRenderer` dispatch, extended with `outputKind`+`mcp23017` props
  - `UISettings.tsx` — kept hex-string normalization for mcp23017 addresses (over upstream's integer-only)
  - `SectionContent.tsx` — kept both `mcp23017` (ours) + `allRemoteInputs` (upstream) props
  - `FormRenderer.tsx` — extended to forward `outputKind` + `mcp23017` to OutputForm
  - `helpers/itemValidation.ts` — extended with `getOutputStats` + expander capacity logic
- ✅ Merge commit `fbe2140` on `feat/expansion-board`
- ✅ TypeScript clean, frontend build clean, Python import smoke ok
- ✅ Installed `gh` CLI, forked upstream to `M4rv-dev/app_black`, pushed branch
- ✅ Rewrote `deploy_backend.sh` to rsync full `boneio/` package (instead of just 2 files)
- ✅ Deployed to BoneIO device: now running 1.4.0dev2 (was 1.3.1)
- ✅ Hypercorn responds 200 on `:8090`, Caddy proxy on `:8091` works for Node-RED
- ✅ Diagnosed missing Node-RED tab in dev: fixed by adding `VITE_NODERED_URL=http://192.168.1.22:8091` to `.env.local`

**Architecture audit** (after merge, before module refactor):
- 3 critical: BoneIOForm (577 lines, ~120 of ours), OutputForm (994 lines, ~150 inner McpHardwareFields), yaml_util.py (split-write embedded ~70 lines)
- 5 duplications: `startsWith('EX_')` × 6 in 5 files, `ADDRESS_OPTIONS` × 2, include-pattern regex × 2 Python, `getOutputStats` IIFE in JSX, `useState outputKind` (should be derived)
- Missing types: `any[]` in 5 files
- Dead code: `BoneIOForm.tsx:37` deprecated `onExpanderAdded` prop

**Plan**: Modules pattern refactor — see `~/.claude/plans/boardy-s-takie-jakie-starry-sun.md`.

**Refactor — completed end-to-end**:
- All phases (0a → B) implemented, verified, committed (7 granular commits), pushed to `fork/feat/expansion-board`, and deployed to BoneIO @ 192.168.1.22.
- Frontend `modules/expander/`: 14 files, ~1065 lines (4 components + 4 hooks + 2 helpers + 3 types + 1 constants + index.ts).
- Backend `boneio/modules/expander/`: 3 files, ~351 lines (yaml_util.py + routes.py + __init__.py with lazy FastAPI import via `__getattr__`).
- BoneIO files slim-down: 7 upstream files lost 657 lines total (–205 in BoneIOForm, –161 in OutputForm, –177 in routes/config.py, etc.). Each retains only 1-2 import + use lines pointing to module.
- Deploy verified: BoneIO 1.4.0dev2 active on device, Hypercorn :8090 returns HTTP 200, `POST /api/config/expander[/remove]` registered (return 422 for empty body — module routes wired correctly), ESPHome connections wstają, expander chips widoczne w display screen list.
- Anti-duplicate checklist 100% clean (no `startsWith('EX_')` outside module, no duplicated MCP address arrays, no inline include-pattern regex, no `useState outputKind`, no `any[]` in module files).

**Commits on this branch since merge `fbe2140`**:
- `96d79b0` — scaffold modules/expander/ + move helpers into module
- `4fe90a0` — scaffold boneio/modules/expander/ backend + slim upstream
- `d2d6d1e` — extract useExpanderManager + <ExpanderManager />
- `a6755ae` — extract useMcpHardware + <McpHardwareFields />
- `bad59e3` — extract OutputAddButton + derive outputKind via hook
- `2eadc44` — dedupe Mcp23017Form constants + OutputTable EX_ check
- `869b32e` — add WORK_LOG.md

**Pending (next session)**:
- Optional: build/inject script POC (task #22) — auto-apply modules onto fresh upstream pull. Pattern now proven on hardware → worth doing when next upstream release lands.
- Eventually: alternative UI skin layer (re-skin) using the same module hooks/helpers.

**Outcome — module pattern validated end-to-end**:
The modules/ pattern works in practice. Future upstream merges should produce minimal conflicts (only the 1-2 line injection points per file). Each subsequent feature should follow the same template: `frontend/.../modules/<feature>/` + `boneio/modules/<feature>/` with public API via `index.ts` / `__init__.py`.

---

## 2026-05-17 — Session 2 (remote_mqtt module: generic MQTT device support)

**Goal**: Add support for arbitrary MQTT-enabled devices (ROPAM alarm panels, third-party sensors, etc.) that don't follow boneIO's topic convention. Scan broker → map topics to entities → Jinja2 `value_template` extraction.

**Scope decisions made up-front** (recorded in plan file):
1. One topic → one entity (multiple `remote_inputs` can subscribe the same topic with different templates).
2. Single broker only — multi-broker deferred (MVP).
3. Jinja2 `value_template` (consistent with HA discovery already used in `integration/homeassistant.py:239`).

**Done — phases 0 → 6 of remote_mqtt module**:

* Phase 0 (`24a3c40`) — scaffold `modules/remote_mqtt/` (backend + frontend) with types/constants/helpers
* Phase 1 (`8b4af6c`) — `POST /api/mqtt/scan` endpoint with wildcard subscribe + collect-and-classify. **Verified live**: scan `#` returned 405 topics in 2s including ROPAM `n64/99/in1..in12`.
* Phase 2 (`3c20007`) — `MqttScanDialog` UI: pattern + duration inputs, results table with type badges, filter, expandable rows.
* Phase 3 (`4ffc39b`) — Jinja2 evaluator (sandboxed, lazy-loaded), `POST /api/mqtt/test-template`, `MqttTopicInspector` with JSON tree + clickable path picker + live debounced preview. Added `Jinja2>=3.1.0` to `pyproject.toml` + installed on device venv.
* Phase 4 (`0ec5d61`) — `MQTTGenericInput(RemoteInputBase)`: subscribes to topic, evaluates `value_template`, coerces to bool, emits `InputEvent`. **Verified live**: tmp config snippet registered `alarm_in1` → log confirmed `"MQTTGenericInput 'alarm_in1' subscribed to topic 'n64/99/in1'"`.
* Phase 5 (`c1ba5b9`) — `MQTTGenericOutput(RemoteOutputBase)`: publishes `command_template` on turn_on/off, optional `state_topic` subscription for real-device state sync. **Verified live**: tmp config snippet registered `alarm_out1` → log confirmed `"Registered MQTT remote output 'alarm_out1' (topic=..., state_topic=...)"`.
* Phase 6 (`0d57bd3`) — `MqttRemoteInputFields` + `MqttRemoteOutputFields` Presentational components: swap in for the `input_id`/`output_id` dropdowns when `remote_source === 'mqtt'`. Live preview reuses backend `/api/mqtt/test-template`. Scan-broker shortcut button included.

**Files**:
* New under `frontend/.../modules/remote_mqtt/` — 16 files, 1263 lines (types + constants + helpers + 5 hooks + 5 components + index.ts).
* New under `boneio/modules/remote_mqtt/` — 5 files, 924 lines (`__init__.py` lazy API, `scanner.py`, `template.py`, `input.py`, `routes.py`, `output.py`).
* Touched upstream: 9 files, +227 lines net (mostly schema YAML additions). Largest single touch is +89 lines in `RemoteInputForm.tsx` (drop-in swap of `input_id` block). The rest are pure 3–13-line injections.

**Architecture (validated again)**:
* Backend module's `__init__.py` lazy-loads FastAPI / Jinja2 / RemoteInputBase / RemoteOutputBase via `__getattr__` — pure helpers (scanner classifier, JSON parser) stay import-cheap.
* Two factory functions (`setup_remote_input`, `setup_remote_output`) live in the module and are called by upstream registrars/manager with 3-line dispatch blocks — full instantiation + HA discovery wiring lives in the module.
* Backend tests: pure Python `python3 -c` smoke tests pass on dev machine; live integration verified on BoneIO @ 192.168.1.22 via tmp config snippets (reverted after each phase).
* Frontend tests: `tsc --noEmit` clean, `npm run build` succeeds, deployed to device.

**Pending — Phase 7 (E2E with real ROPAM device)**:

User noted partway through Phase 5 that their ROPAM alarm config got out of sync (some `out`/`in` MQTT publishes/subscribes missing). The runtime classes (`MQTTGenericInput` / `MQTTGenericOutput`) registered cleanly on tmp configs, but full round-trip with the real alarm wasn't validated. **Phase 7 task**: once ROPAM is re-synced, follow the runbook below to validate the full path.

### Runbook — configure ROPAM via the new UI (Phase 7 validation)

1. **Re-sync the ROPAM alarm** so it publishes/subscribes on its expected topics again (`n64/99/in{1..N}`, `n64/99/temp{1..N}`, `n64/99/status`, `n64/99/out_{1..N}`).
2. **Open BoneIO UI** at `http://192.168.1.22:8091/` (Caddy proxy — for Node-RED tab) and go to **Settings → Remote Devices**.
3. **Add a remote device**:
   * `id: alarm_ropam`, `name: ROPAM Alarm`, `protocol: mqtt`
   * Click **🔍 Scan broker** in the MQTT Settings section, pattern `n64/99/#`, duration 10s — confirm you see all the expected topics with classified types (binary for `in*`, json for `temp*` and `status`).
   * Save.
4. **Add binary-sensor inputs** (Settings → Remote Inputs):
   * For each `n64/99/in{N}`: Add new, pick `alarm_ropam` (auto-sets `remote_source: mqtt`), the form will swap `input_id` for the MQTT fields. Fill `topic: n64/99/inN`, leave `value_template` as default (`{{ value }}`), `payload_on: 1`, `payload_off: 0`. Mode: binary_sensor.
   * Use the test field with payload `1` or `0` to confirm the preview goes green with the right TRUE/FALSE badge.
5. **Add sensor inputs** for `temp*` JSON payloads:
   * For each `n64/99/temp{N}`: Add new, `topic: n64/99/tempN`, `value_template: {{ value_json.val }}`, mode: binary_sensor (or sensor if/when a non-bool extraction is supported by the registrar). Open scan dialog → click the row → click `val` in the JSON tree to auto-fill the template.
   * For `fail` flag of the same temp: separate `remote_input` with same topic, `value_template: {{ value_json.fail }}`, `payload_on: 1`, `payload_off: 0`.
6. **Add `status.zones[0]` flag** (and similar):
   * `topic: n64/99/status`, `value_template: {{ value_json.zones[0] }}`, `payload_on: 1`, `payload_off: 0`.
   * Or AC status: `{{ value_json.ac }}` with same payload mapping.
7. **Add output for relay control**:
   * Settings → Remote Outputs → Add new → `alarm_ropam` device → form swaps to command-topic mode.
   * `topic: n64/99/out_1/cmd`, `command_template: {{ state }}`, `state_topic: n64/99/out_1`, `state_value_template: {{ value }}`, `state_payload_on: 1`, `state_payload_off: 0`.
   * QoS 0, retain off.
8. **Validate end-to-end**:
   * Use `mosquitto_pub -h 192.168.1.4 -u homeassistant -P <pwd> -t n64/99/in1 -m 1` and watch the boneIO log/UI — the input should toggle to active immediately.
   * From boneIO UI, toggle the remote output ON — `mosquitto_sub -h 192.168.1.4 -u ... -t 'n64/99/out_1/+' -v` should see the published command on `out_1/cmd`.
   * If state_topic is wired up, ROPAM republishing `1` on `n64/99/out_1` should pull the boneIO output back in sync.

**If anything in this flow fails** — most likely places to investigate (in order):
1. Topic mismatch (ROPAM publishes `in_1` vs `in1`, or `temp_1` vs `temp1`) — scan output is authoritative, use exactly what the scan shows.
2. JSON payload structure differs from expected (`{"val":6.5,...}` vs `{"value":6.5}`) — open inspector, click in the tree, regenerate template.
3. Cerberus validation reject — drop `/home/boneio/boneio/config.yaml.cache.pkl` and restart so the new schema is re-validated.
4. MQTT subscribe overlap — `MQTTGenericInput` and an existing static subscription on the same topic conflict (one callback per topic key in current bus). Workaround documented in `scanner.py`: use device-specific topic prefixes instead of `#`.

**Commits this session (on `feat/expansion-board`, pushed to fork)**:
* `24a3c40` — `feat(remote_mqtt): scaffold modules/remote_mqtt foundation`
* `8b4af6c` — `feat(remote_mqtt): MQTT topic scanner + POST /api/mqtt/scan endpoint`
* `3c20007` — `feat(remote_mqtt): MqttScanDialog + Scan broker button in RemoteDeviceForm`
* `4ffc39b` — `feat(remote_mqtt): Jinja2 template engine + JSON inspector with live preview`
* `0ec5d61` — `feat(remote_mqtt): MQTTGenericInput — wire generic MQTT topics into InputManager`
* `c1ba5b9` — `feat(remote_mqtt): MQTTGenericOutput — publish commands to arbitrary MQTT topics`
* `0d57bd3` — `feat(remote_mqtt): topic+template form fields for remote inputs/outputs`

**Open follow-ups** (added to task list):
* Phase 7 hardware E2E once ROPAM is re-synced
* Build/inject script POC (task #22) — still deferred, threshold not yet reached.

---

## 2026-05-17 (later) — Pivot to ESPHome-style device-centric pattern

**Why this pivot**: The Phase 0-6 design was *topic-centric* — each `remote_input` row declared its own topic + value_template + payload_on/off inline. User feedback: "stworzyliśmy coś dziwnego" — every other remote device (ESPHome, WLED, boneIO black) is *device-centric*: the device declares its entity catalog, then `remote_inputs` / `remote_outputs` reference entries by `device_id + input_id`. The dropdown UX users expect when adding a remote input (pick from a list of entities the device exposes) didn't work for MQTT because nothing was declared on the device.

**What changed**:

* `boneio/schema/remote_devices.yaml` — for `protocol: mqtt`, the device's `mqtt` block now accepts:
  - `topic_prefix` (display/scope hint)
  - `inputs: [{id, name, topic, value_template, payload_on, payload_off, qos}]`
  - `outputs: [{id, name, topic, command_template, state_topic, state_value_template, state_payload_on/off, qos, retain, output_type}]`

  These extend the existing `{id, name}` schema for boneIO-style devices — the extra fields are simply unused when `device_type=boneio_black`.

* `boneio/schema/remote_inputs.yaml` / `remote_outputs.yaml` — dropped the inline mqtt fields (topic, value_template, payload_*, command_template, state_*, qos, retain). Pure routing rows now: `device_id + input_id/output_id + actions/mode/area/...` — identical to ESPHome remote inputs.

* `boneio/modules/remote_mqtt/input.py` / `output.py` — `setup_remote_input/output` now look up topic + template + payload mapping by `device_id + input_id/output_id` on the remote device's catalog (`_find_device_input` / `_find_device_output`). Friendly log when the device or referenced id is missing.

* `frontend/src/components/UISettings/RemoteInputForm.tsx` / `RemoteOutputForm.tsx` — dropped the topic-centric swap. Standard input_id / output_id dropdown reused; for MQTT devices the option list comes from `selectedDevice.mqtt.inputs` / `.mqtt.outputs` (parallel to ESPHome's `_discovered_binary_sensors`). Hint shows "managed on the device" below the dropdown.

* `frontend/src/components/UISettings/modules/remote_mqtt/components/MqttDeviceEntitiesEditor.tsx` (new) — rendered inside `RemoteDeviceForm.tsx` when `device_type=generic`. Two editable tables (Inputs + Outputs) plus a "Scan & import" workflow: scan dialog opens with the device's topic_prefix, user multi-selects topics, system imports them as inputs with auto-classified templates (`{{ value }}` + `payload_on: "1"` / `payload_off: "0"` for binary, `{{ value_json }}` for JSON, etc.).

* Removed `MqttRemoteInputFields.tsx` + `MqttRemoteOutputFields.tsx` — no longer needed.

* `frontend/src/types/config.ts` — extended `RemoteDeviceEntity.mqtt` with the new `topic_prefix` + `inputs[]` + richer `outputs[]` shapes.

* Polish: id-uniqueness validation in `MqttDeviceEntitiesEditor` (duplicate IDs highlighted red, row tinted, tooltip explains); proper translations for all editor UI strings (en/pl, ~14 keys each).

**What's preserved**: scanner endpoint + UI dialog (now powers Scan & import), Jinja2 evaluator + live preview backend, `MQTTGenericInput` / `MQTTGenericOutput` runtime classes, `MqttTopicDispatcher` (multi-subscriber per topic — now more relevant since one device may have many inputs pointing at the same topic with different templates).

**Verified end-to-end on BoneIO**: tmp `generic_mqtt` device + `remote_inputs` row → service registered `"Registered MQTT remote input 'pivot_test_input' (device=pivot_test_device/ping_in, topic=boneio_test/ping)"` and `"MQTTGenericInput 'pivot_test_input' subscribed to topic 'boneio_test/ping'"` — confirms the device-catalog lookup path works correctly. Test config reverted after.

**Commits**:
* `c0ceb22` — `refactor(remote_mqtt): pivot to device-centric ESPHome-style pattern`
* `437ebd8` — `polish(remote_mqtt): id uniqueness + translations + WORK_LOG pivot rationale`

**Upstream status note**: boneIO has pushed v1.4.0dev3 + v1.4.0dev4 (commits `957a7bd..8f1a21c`) — merged in `ce3d42a`. Module pattern paid off:
* **Zero conflicts** in `modules/expander/` (5 files) and `modules/remote_mqtt/` (8 files) — all 24 module-owned files survived untouched. ~3500 lines of our logic, no manual work needed.
* **6 conflicts**, all small + predictable, all in injection-point files: `schema/remote_outputs.yaml` (kept BOTH our generic-mqtt note AND their momentary/interlock fields), `locales/{en,pl}/common.json` (JSON namespace merge), `SectionContent.tsx` (3 lines: kept mcp23017 prop + savedOutputs extension), `OutputForm.tsx` (kept our `advancedTabContent` extracted-const — DRY), `RemoteOutputForm.tsx` (bigger: adopted their TabsBox restructure, re-applied our MQTT dropdown section + "managed-on-device" hint).
* **Bonus for free**: `MQTTGenericOutput` extends `RemoteOutputBase`, so it now inherits upstream's new `momentary_turn_on/off`, `adjustable_duration`, `interlock_group`, etc. automatically — no module change required. User configures these on the remote_output row; runtime classes pick them up via inheritance.

**Post-merge live verification on BoneIO**:
* Service active, Hypercorn :8090 returns HTTP 200
* `POST /api/mqtt/scan` → 200 (scanner module)
* `POST /api/mqtt/test-template` → 200 (Jinja2 evaluator)
* `POST /api/config/expander` → 422 (route registered, validates payload — both modules wired through)

**Merge commit**: `ce3d42a` on `feat/expansion-board`. Branch now contains 14 commits since base `957a7bd`. The injection-point list above is the runbook for the next upstream merge.

---

## Runbook — next upstream merge

When boneIO releases the next dev tag (1.4.0dev3, 1.4.0, 1.5.x …), follow this. The
goal: pull their changes, re-apply ours, deploy, ship — without re-inventing the wheel.

### Step 1 — pull upstream

```bash
git checkout dev-debian13
git pull origin dev-debian13            # fast-forwards to upstream HEAD
git log --oneline HEAD ^feat/expansion-board | head -30   # what's new
```

### Step 2 — merge into our feature branch

```bash
git checkout feat/expansion-board
git merge dev-debian13                   # produces merge commit; expect SMALL conflicts
git status                               # see unmerged paths
```

### Step 3 — resolve conflicts (the predictable ones)

Conflicts will almost always land at our **7 injection sites**. For each, the goal
is to **keep upstream's new structure** and **re-apply our 1-2 line injection** in
the right place. Our injection points are marked by comments — search for them:

| File | Our injection (marker to look for) |
|------|-------------------------------------|
| `frontend/.../BoneIOForm.tsx` | `import { ExpanderManager } from './modules/expander';` + `<ExpanderManager allOutputs={...} />` after `{/* Expansion board — fully encapsulated module */}` |
| `frontend/.../OutputForm.tsx` | `import { McpHardwareFields, EXPANDER_BOARDS, EXPANDER_OUTPUT_PREFIX, isExpanderOutput, type ExpanderBoardType } from './modules/expander';` + `<McpHardwareFields ... />` call |
| `frontend/.../ArrayTableWidget.tsx` | `import { OutputAddButton, isExpanderOutput, useOutputKind, EXPANDER_OUTPUT_PREFIX } from './modules/expander';` + `<OutputAddButton ... />` + `const outputKind = useOutputKind(editingItem);` |
| `frontend/.../Mcp23017Form.tsx` | `import { MCP_ADDRESS_OPTIONS, MANAGED_EXPANDER_IDS, DEFAULT_ADDRESSES, DEFAULT_ADDRESS_INTEGERS, isExpanderOutput, ... } from './modules/expander';` |
| `frontend/.../helpers/itemValidation.ts` | `import { getOutputStats, isExpanderOutput } from '../modules/expander';` + `isExpanderOutput(dataToSave)` in output validation |
| `frontend/.../tables/OutputTable.tsx` | `import { isExpanderOutput } from '../modules/expander';` + `isExpanderOutput(item)` for badge |
| `frontend/.../components/SectionContent.tsx` | Just `mcp23017` prop passed through to BoneIOForm (no expander call here) |
| `boneio/core/config/yaml_util.py` | `from boneio.modules.expander import split_outputs_for_includes, dedup_outputs_prefer_named` + the 4-line split-write block in `update_config_section()` |
| `boneio/webui/app.py` | `from boneio.modules.expander import register_routes as register_expander_routes` + `register_expander_routes(app)` at end of router registration |
| `boneio/webui/routes/config.py` | Nothing (endpoints moved to module) — if upstream re-introduces an expander endpoint there, decide whether to remove and keep ours |

Tip: `git diff fbe2140..HEAD -- <file>` shows exactly what our refactor put there.

### Step 4 — verify with the anti-duplicate checklist

After resolving conflicts, run these greps to catch any inline duplicates upstream
might have re-introduced (e.g. a fresh `startsWith('EX_')` they added):

```bash
# Must return empty (with the SHIM files exception in #2 — that's intentional)
grep -rn "startsWith.*EX_\|startswith.*EX_" frontend/src/ boneio/ \
  --include="*.ts" --include="*.tsx" --include="*.py" 2>/dev/null \
  | grep -v "modules/expander" | grep -v "__pycache__"

grep -rn "'0x20'.*'0x21'.*'0x22'" frontend/src/ \
  --include="*.ts" --include="*.tsx" 2>/dev/null \
  | grep -v "modules/expander"

grep -rn "^output:.*!include" boneio/ --include="*.py" 2>/dev/null \
  | grep -v "modules/expander" | grep -v "__pycache__"

grep -rn "useState.*outputKind\|setOutputKind" frontend/src/ \
  --include="*.ts" --include="*.tsx" 2>/dev/null

grep -rn "any\[\]" frontend/src/components/UISettings/modules/ \
  --include="*.ts" --include="*.tsx" 2>/dev/null
```

If anything new pops up, fix it (replace with module helper) before committing.

### Step 5 — build chain

```bash
cd frontend && npx tsc --noEmit && npm run build
cd .. && python3 -c "from boneio.bonecli import main; print('bonecli ok')"
python3 -c "from boneio.modules.expander.yaml_util import is_expander_output; print('module ok')"
```

### Step 6 — finalise merge commit

```bash
git commit                # opens editor with merge message; summarise conflicts resolved
git push fork feat/expansion-board
```

### Step 7 — deploy + smoke test

```bash
./deploy_backend.sh                              # full rsync of boneio/ + service restart
sshpass -p '...' ssh boneio@192.168.1.22 "systemctl is-active boneio.service"
curl -sS http://192.168.1.22:8090/ -o /dev/null -w "HTTP %{http_code}\n"
```

Then in UI (`localhost:5173`): regression suite — Add/Remove Expander, edit EX_OUT_*,
badge "expander", dropdown counters, plus a quick poke at any NEW upstream features
to confirm they work.

### Edge cases the module pattern still can't dodge

1. **Upstream renames a file we inject into.** Git marks it as renamed+modified, our
   injection lands in the wrong place or gets dropped. Recovery: `git log --follow`
   the old path, re-apply the injection to the new file.
2. **Upstream changes a function signature we depend on** (e.g. `update_config_section()`
   gets new args). Our backend module helper call breaks. Recovery: adapt the module's
   call site to the new signature; the module's INTERNAL logic stays unchanged.
3. **Upstream ships their own version of our feature** (e.g. their own expander UI).
   Decide: remove ours, merge concepts, or keep both with namespacing. Module isolation
   makes "remove ours" trivial (`rm -rf modules/expander/` + revert injection lines).
4. **Upstream changes Cerberus schema in a way that rejects our EX_* outputs**. Recovery:
   add schema overrides in `boneio/modules/expander/schema_patches.py` (new file, not
   yet built) and apply during boot.

### Threshold for investing in build/inject automation (task #22)

Stop doing manual merges and build the inject script if **any of**:
- More than 2 of our 7 injection points conflict in a single upstream release
- Upstream renames an injection-point file (high-friction recovery)
- We add a 2nd module (e.g. cloud_sync) — automation amortises across modules
- We start managing 3+ branches (e.g. dev + stable backport)

Until then: manual merges with this runbook are cheaper than maintaining a patch system.

---

## How to update this log

After each meaningful work block (typically end of a session, or when finishing a phase):

1. **Update "Active scope"** — current task, phase status table
2. **Append to "Timeline"** — new dated entry with:
   - Goal of the session
   - What was done (✅ bullets)
   - Any decisions made / patterns introduced
   - Current state at end (so next session picks up cleanly)
3. **Mention any new files of architectural significance** in "Architecture decisions"
4. **Don't delete history** — append, don't rewrite. Old entries are evidence of why decisions were made.

Update this file **even if user didn't ask** — it's the persistent context source. Memory pointer
to it in `~/.claude/projects/.../memory/project_work_log.md`.
