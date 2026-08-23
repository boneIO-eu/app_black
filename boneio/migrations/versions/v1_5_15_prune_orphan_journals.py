"""BoneIO 1.5.15 — remove journal directories left behind by reflashing.

``/var/log/journal/`` and log2ram's disk copy hold one subdirectory per
machine-id. journald manages only the one matching ``/etc/machine-id``, so any
other is invisible to ``journalctl --vacuum-*`` and to ``SystemMaxUse`` and is
never cleaned.

They accumulate because the image pipeline truncates ``/etc/machine-id``
(setup_boneio.sh, and the eMMC flasher), so a new id is generated on the next
boot and the previous journal directory stays for good. A controller inspected
in the field had **nine**, eight of them orphaned.

This is not merely wasted disk: log2ram rsyncs the whole tree on every boot, so
every reflash a unit ever had permanently added to its boot time.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    MigrationAction,
    PruneOrphanedJournalDirs,
)

VERSION = "1.5.15"
DESCRIPTION = "Remove orphaned machine-id journal directories"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.15.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        PruneOrphanedJournalDirs(),
    ]
