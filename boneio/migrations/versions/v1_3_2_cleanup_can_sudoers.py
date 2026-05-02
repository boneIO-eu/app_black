"""Remove legacy /etc/sudoers.d/boneio-can (CAN rules now in boneio sudoers).

The CAN interface NOPASSWD rules (/sbin/ip link set can0/can1) were
historically installed as a separate file ``/etc/sudoers.d/boneio-can``
by the old ``FixCanSudoers`` WebUI component.

Since v1.3.0 baseline, these rules live in ``/etc/sudoers.d/boneio``.
The separate file is therefore redundant and should be removed to avoid
duplicated sudoers entries.
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, RemoveFile

VERSION = "1.3.2"
DESCRIPTION = "Remove legacy /etc/sudoers.d/boneio-can (CAN rules already in /etc/sudoers.d/boneio)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of actions: removes the redundant CAN sudoers file.
    """
    return [
        RemoveFile(path="/etc/sudoers.d/boneio-can"),
    ]
