"""Reinstall boneio-system: the panel can see what fills the disk and free it.

Two verbs for the Disk section of Diagnostics. ``disk-usage`` reports, in
bytes, every Docker image with whether a container uses it, the journal and
the apt package cache: the places that grow on ``/`` and that the ``boneio``
account cannot read. ``disk-clean`` takes one of two fixed names, ``docker``
(``docker image prune -a``, which keeps every image a container refers to) or
``apt`` (``apt-get clean``). No path comes from the caller.

Pristine copy first, as in 1.6.22, so ``boneio-helpers-heal.service`` does not
put the old helper back. ``validate="python"`` because a helper that does not
compile would take CAN, the overlay, the hostname, NTP, the broker passwords
and system updates down with it. The sudoers rule from 1.6.8 already covers the
helper.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.40.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.40"
DESCRIPTION = "Show what fills the disk and free it from the panel"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="helpers/boneio-system", dst=dst, mode=0o755,
            owner="root", group="root", validate="python",
        )
        for dst in (f"{_TRUSTED_DIR}/boneio-system", "/usr/sbin/boneio-system")
    ]
