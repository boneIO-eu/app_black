"""Reinstall the migration helper, which may now take boneio out of kmem.

1.6.37 removes the service account from ``kmem``, and the helper refuses any
group removal it does not list itself. Its own migration for the same reason as
1.6.19 and 1.6.23: the helper that runs a plan is the one that has to
understand it, and the runner calls the helper afresh for each version, so
1.6.37 is read by this one. Pristine copy first, so
``boneio-helpers-heal.service`` does not put the old helper back at the next
boot.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.36.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.36"
DESCRIPTION = "Teach the migration helper to take boneio out of kmem"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="helpers/boneio-migrate-v2",
            dst=f"{_TRUSTED_DIR}/boneio-migrate-v2",
            mode=0o755,
            owner="root",
            group="root",
            validate="python",
        ),
        InstallFile(
            src="helpers/boneio-migrate-v2",
            dst="/usr/sbin/boneio-migrate-v2",
            mode=0o755,
            owner="root",
            group="root",
            validate="python",
        ),
    ]
