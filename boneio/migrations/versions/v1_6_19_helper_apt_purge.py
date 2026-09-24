"""Reinstall the migration helper, which can now purge Debian packages.

1.6.20 takes PackageKit and AppStream off the device, and no action could say
that: the helper knew how to install packages, never how to remove them. The
new ``apt_purge`` action simulates the purge first and refuses when apt would
remove anything that is not on the plan's list. A dependency chain is not
allowed to widen what a signed plan says it removes, on whatever a given device
happens to have installed.

This is its own migration because the helper that runs a plan is the one that
has to understand it. A plan carrying ``apt_purge`` handed to the old helper is
refused as a whole, so the new helper has to be in place first; the runner
calls the helper afresh for each version, so 1.6.20 is read by this one.

The pristine copy goes first, as in 1.6.16: ``boneio-helpers-heal.service``
restores from it and would otherwise put the old helper back at the next boot.
``validate="python"`` because this overwrites the only path by which the device
can migrate at all.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.19.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.19"
DESCRIPTION = "Teach the migration helper to purge packages"
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
