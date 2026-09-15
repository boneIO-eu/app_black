"""BoneIO 1.6.0 — require a boneIO administrator to reach Node-RED.

The 1.5.0 pentest's most serious finding was that Node-RED shipped without
``adminAuth``. Its admin API answered anyone who could reach the device through
Caddy, and deploying a flow containing an ``exec`` node is arbitrary code
execution as the container user.

Installing the new ``settings.js`` is what actually closes that on a device
already in the field: the file is only ever written by the 1.3.0 baseline, so
without this migration every existing controller would keep the open editor no
matter what the repository says.

The new settings delegate authentication to boneIO itself, so the accounts are
the ones already in the panel and nothing new has to be set up here.

It takes effect when the container next restarts — on the reboot that follows
an update, or from the Node-RED controls in the panel. The migration framework
has no action for running a command, and giving it one so that this migration
could call ``docker compose restart`` would hand every future migration the
ability to run arbitrary root commands. That is a poor trade for saving one
restart.

docker-compose.yaml is deliberately left alone. Cloud registration edits that
same file, and replacing it to carry one optional environment variable would
put those edits at risk for no real gain: settings.js already falls back to the
default API address on its own.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.0"
DESCRIPTION = "Require a boneIO administrator to sign in to Node-RED (F-01)"
REQUIRES_ROOT = True

_BONEIO_HOME = "/home/boneio"
_BONEIO_USER = "boneio"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.0.

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
