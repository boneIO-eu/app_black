# WLED Cache Extraction — Config Migration v4

## Problem
WLED effects (219), palettes (72), and segments were stored inline in
`config.yaml` under `remote_devices[].wled`. For 7 devices this was ~64KB of
YAML, causing 3-5 second serialization delays on BeagleBone ARM and Axios
timeout errors in the frontend.

## Solution
- Extracted WLED metadata to `.wled_cache.json` (JSON, fast read/write)
- Config migration v4 strips fields from existing configs
- Cache auto-populates from WLED `/json` API on device connect
- New API endpoints serve cached data to frontend
- Defense-in-depth stripping in `update_config_section()`

## Files Changed
- `boneio/core/config/migrations/v4_wled_cache.py` — NEW migration
- `boneio/core/config/migrations/__init__.py` — Schema version 3→4
- `boneio/core/remote/wled_cache.py` — NEW cache module
- `boneio/core/remote/wled.py` — Cache write on discover
- `boneio/webui/routes/remote_devices.py` — New API endpoints
- `boneio/webui/routes/config.py` — `run_in_executor` for async save
- `boneio/webui/app.py` — Cache init at startup
- `boneio/schema/remote_devices.yaml` — Removed fields
- `boneio/core/config/yaml_util.py` — Defense-in-depth stripping
- `frontend/src/components/UISettings/UISettings.tsx` — Timeout 5s→15s
- `boneio/version.py` — 1.5.0dev13
- `CHANGELOG.md` — dev13 entry

## Impact
- Config size: 64KB → 833 bytes (99% reduction)
- Save time on ARM: ~5s → <200ms
- Cache file NOT in backup (auto-regenerates)
