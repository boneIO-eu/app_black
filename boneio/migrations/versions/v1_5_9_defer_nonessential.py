"""BoneIO 1.5.9 — defer non-essential services behind boneIO startup.

Two units start during boot, neither needed to drive I/O, both competing for the
single AM335x core:

    bb-usb-gadgets.service   24.6s   USB networking (192.168.7.2) and ttyGS0
    avahi-daemon.service      2.6s   mDNS / boneio.local

Both are deferred rather than disabled — the USB rescue path and .local
resolution keep working, just after the controller is serving I/O.

On ordering cycles: attaching ``After=boneio.service`` to units that are
``WantedBy=multi-user.target`` previously deadlocked, because boneio.service
itself declared ``After=multi-user.target``. Migration 1.5.6 removed that, which
eliminates the entire class of cycle. Confirmed on hardware with
``systemd-analyze verify default.target`` — no cycles reported.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.5.9"
DESCRIPTION = "Defer bb-usb-gadgets and avahi-daemon behind boneio.service"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.9.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="systemd/dropins/bb-usb-gadgets-defer.conf",
            dst="/etc/systemd/system/bb-usb-gadgets.service.d/50-boneio-defer.conf",
            mode=0o644,
        ),
        InstallFile(
            src="systemd/dropins/avahi-daemon-defer.conf",
            dst="/etc/systemd/system/avahi-daemon.service.d/50-boneio-defer.conf",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
    ]
