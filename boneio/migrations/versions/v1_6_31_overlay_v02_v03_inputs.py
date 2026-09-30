"""Ship the corrected v0.2-v0.3 overlay: P9_11, P9_12 and P9_13 are inputs.

v0.2 and v0.3 boards have no 1-Wire bus and no UART4 — Modbus is on UART1 —
and their board map uses P9_13, P9_12 and P9_11 as inputs IN_26, IN_27 and
IN_28. The overlay the image installed still bound w1-gpio to P9_12 and muxed
UART4 onto P9_11/P9_13, so those three inputs never worked. It also muxed
IN_36 (P8_29) through P8_27's pad.

The image copied its overlays into /boot/dtbs once and nothing updates them
after, so this installs the corrected file into /usr/lib/boneio/overlays/,
where boneio-system treats it as the version every kernel's copy must match.
boneIO's startup check sees copies that differ and asks boneio-system's
``overlay-repair`` to replace them in every /boot/dtbs/<kernel>/ and its
overlays/; uEnv.txt is left alone. The pins change on the next reboot.

Other boards get the file too and have their unused copies of it replaced:
U-Boot loads only the overlay uEnv.txt names, so nothing changes for them.

boneio-system is reinstalled for the replacement, pristine copy first as in
1.6.22 so ``boneio-helpers-heal.service`` does not put the old helper back.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.31.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.31"
DESCRIPTION = "Corrected v0.2-v0.3 overlay: P9_11, P9_12 and P9_13 are inputs"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"
_OVERLAY = "BONEIO-BLACK-PINS-v0.2-v0.3.dtbo"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        *(
            InstallFile(
                src="helpers/boneio-system", dst=dst, mode=0o755,
                owner="root", group="root", validate="python",
            )
            for dst in (f"{_TRUSTED_DIR}/boneio-system", "/usr/sbin/boneio-system")
        ),
        InstallFile(
            src=f"overlays/{_OVERLAY}", dst=f"/usr/lib/boneio/overlays/{_OVERLAY}",
            mode=0o644, owner="root", group="root",
        ),
    ]
