"""BoneIO 1.5.13 — schedule mosquitto like boneIO, since boneIO waits for it.

boneio.service declares ``After=mosquitto.service``, putting the broker directly
on the controller's critical path. It ran at the default ``CPUWeight=100`` while
dockerd, containerd and bb-usb-gadgets contended for the single AM335x core.

Two boots of an otherwise identical configuration:

    boot A: basic.target 31.9s -> mosquitto ready 36.5s -> boneIO exec 51.5s
    boot B: basic.target 31.5s -> mosquitto ready 55.5s -> boneIO exec 55.6s

A 19 s spread in when the broker became ready, and boneIO inherited it. Anything
that gates boneIO needs boneIO's scheduling priority, so mosquitto gets the same
CPUWeight/IOWeight=1000.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.5.13"
DESCRIPTION = "Give mosquitto boneIO's CPU/IO priority (it gates boneIO)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.13.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="systemd/dropins/mosquitto-priority.conf",
            dst="/etc/systemd/system/mosquitto.service.d/50-boneio-priority.conf",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
    ]
