"""BoneIO 1.4.3 — OLED shutdown messages improvement.

Adds a late-phase shutdown OLED service that shows "System stopped"
after the network is already down. Updates boneio.service to only show
"Shutting down..." during actual shutdown (not during restarts).
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
    SystemctlEnable,
)

VERSION = "1.4.3"
DESCRIPTION = "OLED shutdown messages: late-phase service + restart-aware ExecStopPost"
REQUIRES_ROOT = True

_BONEIO_USER = "boneio"
_BONEIO_HOME = f"/home/{_BONEIO_USER}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.4.3.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    template_vars = {
        "BONEIO_USER": _BONEIO_USER,
        "BONEIO_HOME": _BONEIO_HOME,
    }

    return [
        # 1. Install late-shutdown OLED service (runs after network is down)
        InstallFile(
            src="systemd/boneio-oled-shutdown.service",
            dst="/etc/systemd/system/boneio-oled-shutdown.service",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
        SystemctlEnable(unit="boneio-oled-shutdown.service"),

        # 2. Update boneio.service with shutdown-aware ExecStopPost
        InstallFile(
            src="systemd/boneio.service",
            dst="/etc/systemd/system/boneio.service",
            mode=0o644,
            template_vars=template_vars,
            on_change=SystemctlDaemonReload(),
        ),
    ]
