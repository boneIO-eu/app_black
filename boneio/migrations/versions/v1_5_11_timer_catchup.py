"""BoneIO 1.5.11 — stop housekeeping timers from firing all at once at boot.

Debian ships these timers with ``Persistent=true``, so every schedule missed
while the machine was powered off runs immediately at the next boot. A
controller that gets power-cycled rather than left running therefore pays the
full housekeeping bill on startup, on one core, while boneIO is trying to come
up.

Measured contributions to a single boot (systemd-analyze blame):

    fstrim.service          19.2s
    man-db.service           2.5s
    e2scrub_reap.service     2.8s
    dpkg-db-backup.service   1.3s
    logrotate.service        0.5s
    systemd-tmpfiles-clean   0.5s

``Persistent=false`` keeps each schedule but drops the catch-up burst — the job
runs at its next genuine occurrence, while the system is up. RandomizedDelaySec
spreads them so they never coincide.

Note fstrim: dropping catch-up does not skip trimming, it defers it to the next
weekly window with the system running. That is preferable to trimming an SD card
during startup.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.5.11"
DESCRIPTION = "Persistent=false on housekeeping timers (~27s of boot contention)"
REQUIRES_ROOT = True

_TIMERS = [
    "fstrim.timer",
    "man-db.timer",
    "e2scrub_all.timer",
    "dpkg-db-backup.timer",
    "logrotate.timer",
    "systemd-tmpfiles-clean.timer",
]


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.11.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    actions: list[MigrationAction] = [
        InstallFile(
            src="systemd/dropins/timer-no-persistent.conf",
            dst=f"/etc/systemd/system/{timer}.d/50-boneio-no-catchup.conf",
            mode=0o644,
        )
        for timer in _TIMERS
    ]
    actions.append(SystemctlDaemonReload())
    return actions
