"""BoneIO 1.5.6 — take boneIO off the multi-user.target critical path.

boneio.service declared both ``WantedBy=multi-user.target`` and
``After=multi-user.target``. The latter meant it started only once every other
unit pulled in by that target had finished — docker.service alone accounts for
~30 s and containerd.service ~7 s.

Measured on a BeagleBone Black booting from SD:

    network.target        @36.0 s
    containerd.service    @36.0 s  +7.4 s
    docker.service        @43.5 s  +30.3 s
    multi-user.target     @73.8 s
    boneio.service        @89.2 s   <-- first line of Python

boneIO needs neither Docker nor Node-RED to drive I/O, so this was pure
waiting. Dropping the ordering lets it start right after network.target and
mosquitto.service.

Also raises its scheduling priority: with Docker now starting in parallel
rather than beforehand, both compete for the single AM335x core.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.5.6"
DESCRIPTION = "boneio.service: drop After=multi-user.target, raise CPU/IO priority"
REQUIRES_ROOT = True

_BONEIO_USER = "boneio"
_BONEIO_HOME = f"/home/{_BONEIO_USER}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.6.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    template_vars = {
        "BONEIO_USER": _BONEIO_USER,
        "BONEIO_HOME": _BONEIO_HOME,
    }

    return [
        InstallFile(
            src="systemd/boneio.service",
            dst="/etc/systemd/system/boneio.service",
            mode=0o644,
            template_vars=template_vars,
            on_change=SystemctlDaemonReload(),
        ),
    ]
