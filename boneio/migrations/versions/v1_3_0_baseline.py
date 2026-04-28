"""BoneIO 1.3.0 baseline system migration.

Installs all system files and services that were previously embedded in
``setup_boneio.sh``. Runs on every fresh install (image) where the helper
was already installed by the setup script. For existing 1.2.0 installs,
runs after the user completes the bootstrap flow in the WebUI.

This migration is idempotent: each :class:`InstallFile` action compares the
SHA-256 of the rendered content against the existing file before writing.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    AppendLineIfMissing,
    InstallFile,
    MigrationAction,
    RemoveFile,
    SystemctlDaemonReload,
    SystemctlDisable,
    SystemctlEnable,
    SystemctlReload,
    SystemctlRestart,
)

VERSION = "1.3.0"
DESCRIPTION = "Baseline system files: OLED splash, systemd services, mosquitto config, sudoers, Docker, journald"
REQUIRES_ROOT = True

# ---------------------------------------------------------------------------
# Default boneio user (can be overridden via BONEIO_USER env at build time)
# ---------------------------------------------------------------------------
_BONEIO_USER = "boneio"
_BONEIO_HOME = f"/home/{_BONEIO_USER}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.3.0.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    template_vars = {
        "BONEIO_USER": _BONEIO_USER,
        "BONEIO_HOME": _BONEIO_HOME,
    }

    return [
        # ----------------------------------------------------------------
        # 1. OLED helper scripts
        # ----------------------------------------------------------------
        InstallFile(
            src="usr-sbin/oled_msg.py",
            dst="/usr/sbin/oled_msg.py",
            mode=0o755,
        ),
        InstallFile(
            src="usr-sbin/oled_msg.sh",
            dst="/usr/sbin/oled_msg.sh",
            mode=0o755,
        ),

        # ----------------------------------------------------------------
        # 2. OLED boot splash service
        # ----------------------------------------------------------------
        InstallFile(
            src="systemd/boneio-oled-boot.service",
            dst="/etc/systemd/system/boneio-oled-boot.service",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
        SystemctlEnable(unit="boneio-oled-boot.service"),

        # ----------------------------------------------------------------
        # 3. boneIO main systemd service
        #    Clean up legacy "BoneIO.service" (uppercase) from old setup scripts
        #    before installing the canonical lowercase name.
        # ----------------------------------------------------------------
        SystemctlDisable(unit="BoneIO.service"),
        RemoveFile(path="/etc/systemd/system/BoneIO.service"),
        InstallFile(
            src="systemd/boneio.service",
            dst="/etc/systemd/system/boneio.service",
            mode=0o644,
            template_vars=template_vars,
            on_change=SystemctlDaemonReload(),
        ),
        SystemctlEnable(unit="boneio.service"),

        # ----------------------------------------------------------------
        # 4. Hostname-once helper + service
        # ----------------------------------------------------------------
        InstallFile(
            src="usr-local-bin/set-hostname-once.sh",
            dst="/usr/local/bin/set-hostname-once.sh",
            mode=0o755,
        ),
        InstallFile(
            src="systemd/set-hostname-once.service",
            dst="/etc/systemd/system/set-hostname-once.service",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
        SystemctlEnable(unit="set-hostname-once.service"),

        # ----------------------------------------------------------------
        # 5. Mosquitto configuration
        # ----------------------------------------------------------------
        InstallFile(
            src="mosquitto/boneio.conf",
            dst="/etc/mosquitto/conf.d/boneio.conf",
            mode=0o600,
            owner="mosquitto",
            group="mosquitto",
            on_change=SystemctlReload(unit="mosquitto"),
        ),

        # ----------------------------------------------------------------
        # 6. Sudoers for boneio user
        # ----------------------------------------------------------------
        InstallFile(
            src="sudoers/boneio",
            dst="/etc/sudoers.d/boneio",
            mode=0o440,
            validate_cmd="visudo -cf",
        ),

        # ----------------------------------------------------------------
        # 7. Docker daemon logging limits
        # ----------------------------------------------------------------
        InstallFile(
            src="docker/daemon.json",
            dst="/etc/docker/daemon.json",
            mode=0o644,
            on_change=SystemctlRestart(unit="docker"),
        ),

        # ----------------------------------------------------------------
        # 8. Node-RED docker-compose + nginx config
        #    (user-owned: installed to BONEIO_HOME)
        # ----------------------------------------------------------------
        InstallFile(
            src="docker/nodered/docker-compose.yaml",
            dst=f"{_BONEIO_HOME}/docker/nodered/docker-compose.yaml",
            mode=0o644,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        ),
        InstallFile(
            src="docker/nodered/node-red/settings.js",
            dst=f"{_BONEIO_HOME}/docker/nodered/node-red/settings.js",
            mode=0o644,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        ),
        InstallFile(
            src="docker/nodered/nginx/default.conf",
            dst=f"{_BONEIO_HOME}/docker/nodered/nginx/default.conf",
            mode=0o644,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        ),

        # ----------------------------------------------------------------
        # 9. Journald configuration
        # ----------------------------------------------------------------
        InstallFile(
            src="journald/journald.conf",
            dst="/etc/systemd/journald.conf",
            mode=0o644,
            on_change=SystemctlRestart(unit="systemd-journald"),
        ),
    ]
