"""BoneIO 1.5.7 — fit journald inside the 128 MB log2ram tmpfs.

/var/log is a 128 MB tmpfs (log2ram). journald.conf shipped with
``SystemMaxUse=300M`` and ``SystemKeepFree=300M``, so it was told to keep more
free space than the filesystem holds in total — an unsatisfiable constraint that
made it rotate and discard continuously.

Observed on a controller with 18 h uptime:

* ``journalctl -b`` returned 330 lines and the early-boot timeline was gone,
  which is why the first boot analysis had to be redone from a serial capture
* SSH and the serial getty both hung after the sshd banner, inside PAM —
  ``lastlog``, ``wtmp`` and ``wtmpdb`` all write to /var/log. A fresh boot
  logged in normally, so the failure only shows up after hours of runtime.

Note on /etc/log2ram.conf: it contains ``JOURNALD_AWARE=true`` twice. Since both
occurrences set the same value and the file is shell-sourced, this is cosmetic
and is deliberately left alone rather than overwriting a package-managed config.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlRestart,
)

VERSION = "1.5.7"
DESCRIPTION = "journald limits sized for the 128MB log2ram tmpfs"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.7.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="journald/journald.conf",
            dst="/etc/systemd/journald.conf",
            mode=0o644,
            on_change=SystemctlRestart(unit="systemd-journald"),
        ),
    ]
