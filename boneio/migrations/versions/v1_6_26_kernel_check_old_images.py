"""Reinstall boneio-system: the kernel check reads the overlay U-Boot reads.

A controller on an early image (kernel 6.18.2-bone12, never upgraded) was
reported critical — "do not restart, call support" — after updating to
1.6.0.dev19. Early images and the old UPGRADE.md put the overlay only under
``/boot/dtbs/$uname_r/overlays/`` and loaded it from there by full path; the
check looked for a copy in ``/boot/dtbs/$uname_r/`` before it looked at the
path U-Boot actually reads, and repair refused to copy from the boot kernel's
own directory — the only copy such a controller has.

The check now follows what U-Boot does: the path as written, or the bare name
in the boot kernel's directory; every ``uboot_overlay_addrN`` key, and for a
key assigned twice, the last value. When the next boot is this one again —
same kernel, uEnv.txt untouched since boot, the boneIO overlay live in the
device tree — a file it cannot find is not reported as critical. Pristine copy
first, as in 1.6.22, so ``boneio-helpers-heal.service`` does not put the old
helper back.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.26.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.26"
DESCRIPTION = "Kernel check follows the overlay path U-Boot reads"
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
