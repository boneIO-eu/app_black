"""BoneIO 1.5.14 — shrink journal preallocation so log2ram stops copying holes.

log2ram rsyncs /var/log between tmpfs and disk on every boot. It passes
``--no-whole-file``, which forces rsync's delta-transfer algorithm even for a
local copy, so rsync checksums the **apparent** size of every file — including
the holes in sparse files — on a 1 GHz single-core AM335x.

journald preallocates each journal file up to ``SystemMaxFileSize``, so those
files are mostly holes. Measured on a controller with SystemMaxFileSize=8M:

    14 journal files, 11 MB allocated, 112 MB apparent
    log2ram at boot: rsync moved 134.6 MB, unit took 18.3 s

After dropping SystemMaxFileSize to 2M (and SystemMaxUse to 24M):

    rsync moved 21.4 MB, log2ram took 7.0 s
    I/O ready went from 75.4 s to 65.3 s

Note that ``journalctl --disk-usage`` reports allocated bytes and showed 22 MB
throughout, so it hides this entirely. Use ``du --apparent-size`` when judging
log2ram cost.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlRestart,
)

VERSION = "1.5.14"
DESCRIPTION = "Smaller journal files so log2ram stops rsyncing sparse holes"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.14.

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
