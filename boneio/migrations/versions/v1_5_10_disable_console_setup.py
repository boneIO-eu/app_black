"""BoneIO 1.5.10 — disable console keymap/font setup on a headless controller.

    keyboard-setup.service   5.0s
    console-setup.service    0.8s

Both configure a console keymap and font. The controller has no keyboard and no
local console beyond the serial getty, which does not use them.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    MigrationAction,
    SystemctlDaemonReload,
    SystemctlDisable,
)

VERSION = "1.5.10"
DESCRIPTION = "Disable keyboard-setup and console-setup (5.8s of boot time)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.10.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        SystemctlDisable(unit="keyboard-setup.service"),
        SystemctlDisable(unit="console-setup.service"),
        SystemctlDaemonReload(),
    ]
