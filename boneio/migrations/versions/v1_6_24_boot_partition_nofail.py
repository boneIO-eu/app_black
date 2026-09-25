"""A damaged FAT boot partition no longer stops the controller from booting.

``/boot/firmware`` is the small FAT partition a PC can open: ``sysconf.txt``,
``boneio.txt``. Nothing the boot needs lives there — U-Boot reads ``uEnv.txt``
and the kernel from the ext4 root — yet fstab listed it without ``nofail``, so
local-fs.target required it. FAT has no journal, and a power cut while it is
mounted read-write leaves it dirty; the test controller had two ``FSCK*.REC``
files on it, clusters fsck.fat had already had to rescue. The day
fsck.fat or the mount gives up, systemd drops to emergency mode, with a healthy
root filesystem, no network and no panel — a controller in a cabinet that only
a serial console can bring back.

With ``nofail`` the partition is still checked and mounted at every boot. If it
cannot be, the boot carries on without it and the failed unit is visible in
``systemctl --failed``.

Images from this release carry the option in the fstab the eMMC flasher
writes; this is for controllers already installed. Needs the helper from
1.6.23.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.24.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    FstabAddOptions,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.6.24"
DESCRIPTION = "Boot even when the FAT boot partition cannot be mounted"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        FstabAddOptions(mountpoint="/boot/firmware", options=["nofail"]),
        # The fstab generator runs again, so the running system matches the
        # file and systemd stops warning that fstab changed under it.
        SystemctlDaemonReload(),
    ]
