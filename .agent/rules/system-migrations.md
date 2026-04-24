# System Migrations — Rules for AI Agents

This document defines the **mandatory rules** for modifying system-level (OS)
files on the BoneIO appliance. It complements the Python package and is the
**single source of truth** for system configuration.

Read this **before** you propose any change that touches:

- `/etc/**` (systemd, sudoers, mosquitto, docker, journald, ...)
- `/usr/sbin/**`, `/usr/local/bin/**`
- Any file outside the `boneio` Python package that is expected to live on the
  installed target machine.

---

## 1. Architecture (must-know)

```
boneio/migrations/
├── actions.py                # Action types: InstallFile, RemoveFile,
│                               SystemctlEnable/Restart/Reload, AppendLineIfMissing
├── runner.py                 # MigrationRunner: discovers, tracks, applies
├── __init__.py               # Exports MigrationRunner, MigrationStatus
├── bootstrap/
│   ├── boneio-migrate        # Privileged helper (installed to /usr/sbin/)
│   ├── sudoers-migrate       # NOPASSWD sudoers fragment for helper
│   └── install-helper.sh     # One-time installer (needs sudo password)
├── versions/
│   ├── __init__.py
│   └── v1_3_0_baseline.py    # plan() -> list[MigrationAction]
└── assets/
    ├── MANIFEST.sha256       # Auto-generated, DO NOT EDIT BY HAND
    ├── systemd/*.service
    ├── sudoers/*
    ├── mosquitto/*.conf
    ├── docker/*.json
    ├── journald/*.conf
    ├── usr-sbin/*
    └── ...
```

Applied-flag directory on target: `/var/lib/boneio/migrations.d/<version>.applied`

---

## 2. Golden rules (non-negotiable)

### 2.1 Never edit an already-released migration
Once `vX_Y_Z_*.py` is shipped in a released version, it is **immutable**.
Users who already ran it will not re-execute it, so any retroactive edit
is silently lost.

- **Wrong:** "Fix" `v1_3_0_baseline.py` to install a new file.
- **Right:** Create `v1_4_0_add_foo.py` with the new action.

### 2.2 Every system-file change = one new migration
If a change touches a file outside the Python package, it **must** ship as a
new migration module. No exceptions. This includes:

- Adding a systemd service
- Changing a sudoers entry (even a single line)
- New content in `/etc/**`
- New executable in `/usr/sbin/` or `/usr/local/bin/`

### 2.3 Migrations must be idempotent
`InstallFile` uses SHA256 comparison; re-running is a no-op. Any custom
logic you add must follow the same rule — check state first, act second.

### 2.4 Never write system files directly from `setup_boneio.sh`
`setup_boneio.sh` is the **one-shot image builder**. System-level files
(configs, services, sudoers) must come from migrations. The script only:

- Installs apt packages
- Creates empty directories
- Bootstraps data-only files (e.g. `mosquitto passwd` database)
- Runs `boneio-migrate --apply-all` after pip install

### 2.5 Never hardcode paths in migration code
Use the template variable mechanism. Available vars in migrations:

- `{{BONEIO_HOME}}` → `/home/boneio`
- `{{BONEIO_USER}}` → `boneio`
- `{{VENV_PATH}}` → `/home/boneio/boneio/venv`

### 2.6 Assets are bytes, migrations are Python
- **Assets** (`assets/**`) = literal file contents to copy. Binary-identical.
- **Migrations** (`versions/vX_Y_Z_*.py`) = declarative list of actions.
- Never embed file contents as strings inside Python migration modules.

### 2.7 Regenerate MANIFEST.sha256 after every asset change
```bash
python3 scripts/generate_manifest.py
```
Without the hash, `InstallFile` logs a warning and skips integrity check.
CI should fail if `MANIFEST.sha256` is stale.

### 2.8 Helper privilege boundary
The `boneio-migrate` helper runs as **root** via NOPASSWD sudoers, and **only**
accepts JSON plans on stdin from the `boneio` user. Never extend it to:

- Execute arbitrary shell
- Accept file paths from user input without validation
- Run on behalf of any user other than `boneio`

---

## 3. How to add a new migration (cookbook)

Scenario: you need to update `/etc/sudoers.d/boneio` to allow a new command.

### Step 1 — Modify the asset
Edit `boneio/migrations/assets/sudoers/boneio` with the new content.

### Step 2 — Create the migration module
Create `boneio/migrations/versions/v1_4_0_sudoers_can2.py`:

```python
"""Add CAN2 interface management to boneio sudoers."""
from __future__ import annotations
from boneio.migrations.actions import InstallFile, SystemctlReload

VERSION = "1.4.0"
DESCRIPTION = "Extend sudoers with CAN2 ip link commands"
REQUIRES_ROOT = True


def plan() -> list:
    """Return declarative list of actions."""
    return [
        InstallFile(
            src="sudoers/boneio",
            dst="/etc/sudoers.d/boneio",
            mode=0o440,
            owner="root",
            group="root",
        ),
        # sudoers needs no reload, but if you changed a systemd unit:
        # SystemctlReload(),
    ]
```

### Step 3 — Regenerate manifest
```bash
python3 scripts/generate_manifest.py
```

### Step 4 — Verify locally
```python
python3 -c "
from boneio.migrations.versions.v1_4_0_sudoers_can2 import plan, VERSION
print(VERSION, len(plan()))
"
```

### Step 5 — Ship
Bump `boneio/version.py`, commit both the asset and the migration together.

---

## 4. Upgrade path contract

The runner guarantees:

- User on **1.2.0** upgrading to **1.7.0** (skipping 1.3/1.4/1.5/1.6)
  applies **all** pending migrations in version order.
- Migrations are **transactional per-version**: if 1.5.0 fails, 1.3.0 and 1.4.0
  remain applied; next restart resumes at 1.5.0.
- A user who manually edited a managed system file will see a SHA256 mismatch
  warning; policy is currently **overwrite** (declarative = single source of
  truth). If this ever changes, document the new policy here.

---

## 5. What does NOT belong in this system

- **apt install** — not implemented; requires new `AptInstall` action
- **User-facing config** (`/home/boneio/boneio/config.yaml`) — owned by user
- **Per-device secrets** (MQTT passwords, hostnames) — bootstrapped in
  `setup_boneio.sh` or generated at first boot
- **Python package content** — managed by `pip`

If you need one of these, **stop and ask the user** before extending the
migration system.

---

## 6. Testing discipline

Before shipping a new migration:

1. **Unit test** `plan()` returns expected actions.
2. **Dry-run** the migration against a sandbox root dir (see
   `boneio-migrate --root /tmp/test-root --no-sudo`).
3. **Integration test** on a real BBB with a previous release installed.
4. Verify the `.applied` flag appears after success.
5. Run `boneio-migrate --status` — it must show the new version as applied.

---

## 7. Quick reference — files to touch for common changes

| Change | Asset | New migration module | Notes |
|---|---|---|---|
| New systemd service | `assets/systemd/foo.service` | `InstallFile` + `SystemctlEnable` | `on_change: systemctl daemon-reload` |
| Update service unit | edit existing asset | `InstallFile` + `SystemctlRestart` | Same `dst` path |
| New sudoers rule | edit `assets/sudoers/boneio` | `InstallFile` | mode `0o440` mandatory |
| New OLED script | `assets/usr-sbin/new.py` | `InstallFile` mode `0o755` | |
| journald tweak | edit `assets/journald/journald.conf` | `InstallFile` + `SystemctlRestart("systemd-journald")` | |
| mosquitto config | edit `assets/mosquitto/boneio.conf` | `InstallFile` + `SystemctlReload("mosquitto")` | |

---

## 8. Red flags (stop and think)

If a future change triggers any of these, **pause and re-read this document**:

- "Let me just edit `v1_3_0_baseline.py`..." → **NO**, create new migration
- "Let me add a `cat > /etc/...` in `setup_boneio.sh`..." → **NO**, add migration
- "Let me bypass the helper with `os.system('sudo ...')`..." → **NO**, use helper
- "Let me put the config content in a Python string..." → **NO**, use asset file
- "Let me skip `generate_manifest.py` this time..." → **NO**, CI will break

---

_Last updated: 2026-04-24. When updating this document, also bump the
reference in the main `rules.md` if one is added._
