"""Reinstall boneio-containers: an image pull may take fifteen minutes.

Every compose verb ran under the helper's 120 s limit. Pulling a new Node-RED
image onto a BeagleBone takes longer than that, so an update from the panel
failed with ``timed out after 120s: docker compose ... pull node-red`` and was
rolled back to the old tag. ``pull`` and ``pull-nodered`` now get 900 s, as
the Caddy pull already did; every other verb keeps 120 s.

Pristine copy first, as in 1.6.21, so ``boneio-helpers-heal.service`` does not
put the old helper back. ``validate="python"`` because a helper that does not
compile would take Node-RED and Caddy control down with it. The sudoers rule
from 1.6.5 already covers the helper.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.39.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.39"
DESCRIPTION = "Give a container image pull fifteen minutes"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="helpers/boneio-containers", dst=dst, mode=0o755,
            owner="root", group="root", validate="python",
        )
        for dst in (f"{_TRUSTED_DIR}/boneio-containers", "/usr/sbin/boneio-containers")
    ]
