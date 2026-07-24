# Invalidation of Config Cache on Quick Action / Config Update

## Problem Description
When adding a Quick Action (via `POST /api/config/quick-action`) or saving a config section (via `PUT /api/config/{section}`), the changes were written to `config.yaml` on disk and hot-applied to in-memory input objects. However, when navigating to or refreshing the Settings UI (`UISettings`), the updated actions/inputs were not visible until restarting the application.

## Cause
1. `GET /api/config` calls `get_parsed_config()` in `boneio/webui/routes/config_core.py`.
2. When route cache `_config_cache["data"]` was set to `None` by `invalidate_config_cache()`, `get_parsed_config()` fetched source config via `manager.config_helper.get_config()`.
3. `ConfigHelper` maintained its own internal in-memory cache (`self._config_cache`), which was **never updated** when `invalidate_config_cache()` was invoked.
4. As a result, `manager.config_helper.get_config()` returned stale in-memory config from startup, causing `GET /api/config` to serve outdated configuration to the UI.

## Resolution — In-Place Cache Update
Full YAML reload on BeagleBone Black takes ~20-30 seconds due to Cerberus validation. Instead of invalidating the cache and forcing a full reload, the config is updated **in-place** in memory:

1. Added `update_config_section(section, data)` method to `ConfigHelper` (`boneio/core/config/config_helper.py`). It patches `self._config_cache[section]` directly without any disk I/O.
2. Updated `invalidate_config_cache()` in `boneio/webui/routes/config_core.py` to accept optional `section` and `section_data` parameters. When provided, it calls `config_helper.update_config_section()` to patch the in-memory config instantly.
3. Updated callers:
   - `config_actions.py` quick-action endpoint: passes `section` and `entries` after YAML save
   - `config_core.py` PUT `/config/{section}` endpoint: passes `section` and `data` after YAML save
4. Callers that don't know which section changed (backup restore, modbus) continue calling `invalidate_config_cache()` without arguments — the next `GET /api/config` will trigger a fast reload (~0.5-1s via `reload_config()`).
5. Added unit tests in `tests/unit/webui/test_config_cache.py`.

## Frontend — Proactive Duplicate Detection
Added proactive duplicate output/cover detection in `QuickActionSheet.tsx`:

1. When the dialog opens, `GET /api/config` is fetched to get existing actions for the input.
2. After the user selects a click type and an output/cover, the component checks if that output is already assigned to the selected click type.
3. If a duplicate is detected, a yellow warning alert is displayed under the entity picker: *"To wyjście jest już przypisane do tego typu kliknięcia"* (PL) / *"This output is already assigned to this click type"* (EN).
4. The backend still enforces the 409 conflict as a safety net.
5. i18n keys: `quick_action.already_assigned` in `pl/common.json` and `en/common.json`.
