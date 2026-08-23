"""BoneIO 1.5.17 — start the lingering user manager last, not during boot.

Migration 1.5.16 enabled lingering so SSH logins stop paying the ~4.1 s startup
of ``user@1000.service``. The side effect is that the manager also starts at
boot and, on a single-core AM335x, took CPU from boneIO.

Measured progression:

    no lingering                      I/O ready 65.3-66.7s, login after gap 6.9s
    lingering, unordered              I/O ready 71.1s,      login after gap 2.8s
    lingering, After=boneio.service   I/O ready 72.3s       <- no help
    lingering, After=multi-user       I/O ready 70.6s, user@1000 starts at 103s

``After=boneio.service`` is useless here and it is worth recording why:
boneio.service is ``Type=simple``, so systemd marks it active the instant it
execs (~51 s) while its Python imports and hardware init continue for another
~20 s. Ordering against "active" put the user manager straight into that window.

``multi-user.target`` is only reached once everything else has started, so
ordering against it puts the user manager genuinely last — confirmed by its job
starting at 103 s, well past I/O readiness.

The residual difference is not this unit. With the manager deferred, the cost
that remains is ``systemd-logind`` (6.8 s, starting at 49.8 s) and
``user-runtime-dir@1000``, which lingering makes logind do at boot. That is
about 1.7 s; the rest of the gap in the numbers above was log2ram growing as
repeated test logins filled the journal.

A login attempted before multi-user.target waits for the manager. Deliberate:
boot happens on every power cycle and delays real I/O, while logging in is
occasional maintenance.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.5.17"
DESCRIPTION = "Order the lingering user manager after multi-user.target"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.17.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="systemd/dropins/user-manager-defer.conf",
            dst="/etc/systemd/system/user@1000.service.d/50-boneio-defer.conf",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
    ]
