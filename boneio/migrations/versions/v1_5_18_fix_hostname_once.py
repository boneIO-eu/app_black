"""BoneIO 1.5.18 — fix devices stuck with a hostname that doesn't match their MAC.

``set-hostname-once.service`` runs once at first boot, derives ``blk<mac>``
from the Ethernet MAC and calls ``hostnamectl set-hostname``. The script had
two bugs:

1. It only checked ``/sys/class/net/eth0/address``. On Debian 13 the onboard
   NIC can enumerate as ``end0`` (predictable network interface naming), so
   the MAC lookup silently found nothing.
2. ``systemctl disable set-hostname-once.service`` ran unconditionally, even
   outside the ``if`` branch that succeeds. So the one lookup failure above
   permanently disabled the service with no retry on a later boot — the
   system hostname was stuck on whatever the image shipped with.

Meanwhile boneIO's own ``get_network_info()`` computes the MQTT serial number
live, on every start, and already falls back from ``eth0`` to ``end0``. The
result: devices report the *correct* serial over MQTT but keep a *stale*
system hostname forever, since the broken service already burned its one
attempt and disabled itself.

This migration reinstalls the fixed script (eth0/end0 fallback, disable only
on success) and re-enables + re-runs the service immediately, so already
affected devices are corrected without waiting for a reboot.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlEnable,
    SystemctlRestart,
)

VERSION = "1.5.18"
DESCRIPTION = "Fix set-hostname-once.sh eth0/end0 fallback and disable-on-failure bug"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.18.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="usr-local-bin/set-hostname-once.sh",
            dst="/usr/local/bin/set-hostname-once.sh",
            mode=0o755,
        ),
        # The old script may have disabled itself after a failed lookup on a
        # previous boot; re-enable so future boots retry too.
        SystemctlEnable(unit="set-hostname-once.service"),
        # Run it now with the fixed script instead of waiting for a reboot.
        SystemctlRestart(unit="set-hostname-once.service"),
    ]
