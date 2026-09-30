"""Reinstall boneio-system: an OS update clears apt's cache when short of room.

``os-update-run upgrade`` refuses below 300 MB free on ``/``, which is right
for dpkg and a kernel's initramfs, but it counted apt's own downloads against
the device. ``apt-get clean`` ran only after a successful upgrade, so packages
downloaded earlier — unattended-upgrades included — could be exactly what kept
the next upgrade from starting. Found on a controller with a 2.9 GB eMMC
rootfs: 277 MB free, 144 MB of it in ``/var/cache/apt/archives``.

Now, when short, the upgrade runs ``apt-get clean`` first and checks again;
apt downloads whatever it needs anyway. ``os-update-state`` reports
``apt_cache_mb``, so the panel offers the upgrade when clearing the cache
would make room, and says it will.

Pristine copy first, as in 1.6.22, so ``boneio-helpers-heal.service`` does not
put the old helper back. ``validate="python"`` because a helper that does not
compile would take CAN, the overlay, the hostname, NTP, the broker passwords
and system updates down with it. The sudoers rule from 1.6.8 already covers the
helper.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.30.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.30"
DESCRIPTION = "Clear apt's cache before an OS update that is short of room"
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
