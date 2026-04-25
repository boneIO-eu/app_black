"""Fix OLED boot splash timing and stale messages.

Changes:
- boneio-oled-boot.service: explicit Before=BoneIO.service ordering,
  ConditionPathExists guard, ExecStop transition message
- BoneIO.service: remove ExecStartPre (early_oled in bonecli handles startup
  display), add ExecStopPost to show stopped message, add After=boneio-oled-boot.service
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.3.0dev18"
DESCRIPTION = "Fix OLED boot splash ordering and stale display messages"
REQUIRES_ROOT = True

_BONEIO_USER = "boneio"
_BONEIO_HOME = f"/home/{_BONEIO_USER}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    template_vars = {
        "BONEIO_USER": _BONEIO_USER,
        "BONEIO_HOME": _BONEIO_HOME,
    }

    return [
        # Updated boot splash service with explicit ordering
        InstallFile(
            src="systemd/boneio-oled-boot.service",
            dst="/etc/systemd/system/boneio-oled-boot.service",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
        # Updated main service: no ExecStartPre, added ExecStopPost
        InstallFile(
            src="systemd/BoneIO.service",
            dst="/etc/systemd/system/BoneIO.service",
            mode=0o644,
            template_vars=template_vars,
            on_change=SystemctlDaemonReload(),
        ),
    ]
