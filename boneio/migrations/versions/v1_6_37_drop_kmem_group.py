"""BoneIO 1.6.37 — take the service account out of ``kmem``.

The image's default account, which boneIO runs as, came with membership of
``kmem``. That group owns ``/dev/mem`` and ``/dev/port`` with read access, and
the BeagleBone kernel is built without ``CONFIG_STRICT_DEVMEM``, so anything
running as ``boneio`` could read all of physical memory: the shadow hashes, the
SSH host keys, the memory of root's own processes. The audit of blk239bb2 on
dev31 found it (C-01); it undoes the line F-04 drew between boneio and root.

Nothing boneIO runs opens either device — GPIO goes through
``/dev/gpiochip*`` (libgpiod), I2C through ``/dev/i2c-*`` — so the membership
goes and nothing replaces it.

The running service keeps the groups it started with; the change holds from
its next start. Idempotent: a device imaged without the membership, or one
that has been through this already, skips it.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.37.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, RemoveFromGroup

VERSION = "1.6.37"
DESCRIPTION = "Take boneio out of kmem: no reading physical memory (F-04, C-01)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.37.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [RemoveFromGroup(account="boneio", group="kmem")]
