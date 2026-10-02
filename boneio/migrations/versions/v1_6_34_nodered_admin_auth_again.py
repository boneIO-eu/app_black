"""BoneIO 1.6.34 — install the Node-RED settings that require a login, again.

1.6.0 installed ``settings.js`` with ``adminAuth`` delegated to boneIO, and
recorded itself as applied. On the SD card images that record did not mean the
file was still there: the images are built on a rootfs that had already been
through setup once, so 1.6.0 counted as done, and the image script's own step
then wrote its four-line ``settings.js`` over the real one — no ``adminAuth``.
Every controller flashed from such an image (seen on dev29, blk239bb2, audit
finding A-02) ran Node-RED's editor open to anyone who could reach the device,
which is F-01 back: a flow with an ``exec`` node is code execution.

The same file again, under a new version so it is applied once more on every
device. Where the file is already the right one, the helper finds the hash
matching and writes nothing.

The running container keeps the settings it started with. boneIO restarts it
on its own after starting, when the editor answers without a login while this
file asks for one (see :mod:`boneio.core.nodered_guard`), so an update is
enough and no reboot is needed.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.34.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.34"
DESCRIPTION = "Install the Node-RED settings that require a login, again (F-01, A-02)"
REQUIRES_ROOT = True

_BONEIO_HOME = "/home/boneio"
_BONEIO_USER = "boneio"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.34.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="docker/nodered/node-red/settings.js",
            dst=f"{_BONEIO_HOME}/docker/nodered/node-red/settings.js",
            mode=0o644,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        ),
    ]
