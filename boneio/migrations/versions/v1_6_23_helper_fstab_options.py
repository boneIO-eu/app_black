"""Reinstall the migration helper, which can now add options to fstab entries.

1.6.24 marks the FAT boot partition ``nofail``, and no action could say that:
fstab differs from device to device, so ``install_file`` cannot ship it whole.
The new ``fstab_add_options`` action edits the options field of one mount
point's entries and nothing else, and only with options the helper itself
lists for that mount point.

This is its own migration for the same reason as 1.6.19: the helper that runs
a plan is the one that has to understand it, and the runner calls the helper
afresh for each version, so 1.6.24 is read by this one. Pristine copy first, so
``boneio-helpers-heal.service`` does not put the old helper back at the next
boot.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.23.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.23"
DESCRIPTION = "Teach the migration helper to add fstab options"
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
