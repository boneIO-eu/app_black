# Refactor: config.py → 5 sub-modules

## Date: 2026-07-20

## Problem
`boneio/webui/routes/config.py` had ~1880 lines — difficult to navigate and maintain.

## Solution
Split into 5 logical modules + 1 re-export facade:

| Module | Lines | Responsibility |
|--------|-------|----------------|
| `config_core.py` | ~460 | State, cache, `GET/PUT /config`, reload, checksum |
| `config_backups.py` | ~560 | Download/restore/create/list/delete backups, inspect |
| `config_files.py` | ~100 | File browser (`/files` endpoints) |
| `config_actions.py` | ~300 | Quick actions, device type validation |
| `config_discovery.py` | ~170 | HA discovery, interlock groups, Loxone |
| `config.py` (facade) | ~110 | Re-exports everything for backward compatibility |

## Architecture

```
config.py (facade, re-exports)
    ├── config_core.py      ← owns `router`, state vars, cache
    ├── config_backups.py   ← imports router from config_core
    ├── config_files.py     ← imports router from config_core
    ├── config_actions.py   ← imports router from config_core
    └── config_discovery.py ← imports router from config_core
```

All sub-modules import `router` from `config_core` and register their routes on it.
Existing `from boneio.webui.routes.config import ...` imports continue to work.

## Verification
- ✅ All 31 functions from original are present in new files (AST diff)
- ✅ Executable code is identical (only comments/docstrings reformatted)
- ✅ All syntax checks pass
- ✅ No circular dependencies (all sub-modules import only from `config_core`)
- ✅ External imports (`app.py`, `modbus.py`, `__init__.py`) continue to work
- ✅ `get_config_checksum` re-export fixed (was missing from import, duplicate in `__all__`)
