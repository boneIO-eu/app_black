"""Reinstall boneio-system: an OS update asks apt how much room it needs.

``os-update-run upgrade`` let any upgrade start with 300 MB free on ``/``. A
controller a year behind has well over a hundred packages to bring in, and on
the 2.9 GB eMMC rootfs that was not enough: apt downloaded them, dpkg filled
``/`` to zero while unpacking, and the run ended in ``dist-upgrade failed
(rc=100)`` with the downloads still on disk.

Now, after ``apt-get update``, the helper runs ``apt-get --assume-no
dist-upgrade`` and reads apt's own figures — what is still to download, what
the packages grow by — and requires that plus a 100 MB margin for the new
kernel's initramfs and dpkg's working copies, never less than the old 300 MB.
A check records the same figure, and the panel warns against it instead of the
flat minimum. The apt cache is cleared before every upgrade and after a failed
one, and ``dpkg --configure -a`` runs before the gate, so a device left full by
a failed run can be repaired from the panel.

Pristine copy first, as in 1.6.22, so ``boneio-helpers-heal.service`` does not
put the old helper back. ``validate="python"`` because a helper that does not
compile would take CAN, the overlay, the hostname, NTP, the broker passwords
and system updates down with it. The sudoers rule from 1.6.8 already covers the
helper.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.33.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.33"
DESCRIPTION = "Check an OS update against the room apt says it needs"
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
