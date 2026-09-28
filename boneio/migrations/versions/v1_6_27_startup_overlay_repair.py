"""Reinstall boneio-system: the startup overlay check can repair again.

At every start boneIO checks that ``/boot/dtbs/$uname_r/`` holds a boneIO
overlay, and when it does not, copies one in. It did the copy by piping a plan
to the legacy ``boneio-migrate``, which 1.6.6 removed — so on every 1.6.x
controller the check only logged "boneio-migrate helper not installed" and
repaired nothing. The v2 helper takes signed plans only, rightly, so an ad-hoc
plan cannot go there either.

boneio-system gains ``overlay-repair``, a verb with no arguments: the kernel
check's repair, for the overlay uEnv.txt names, from VALID_OVERLAYS only and
only from under /boot/dtbs. Unlike the repair after a system update it never
edits uEnv.txt — nobody is watching at startup — and it also fills the boot
kernel's ``overlays/`` so the check does not ask again on every boot. Pristine
copy first, as in 1.6.22, so ``boneio-helpers-heal.service`` does not put the
old helper back. The sudoers rule from 1.6.8 already covers the helper.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.27.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.27"
DESCRIPTION = "Startup overlay check repairs through boneio-system"
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
