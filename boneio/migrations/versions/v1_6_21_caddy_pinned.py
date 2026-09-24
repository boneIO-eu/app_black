"""Pin Caddy to an exact version, and let the panel move it there.

Caddy ran ``caddy:2-alpine``: whatever that tag meant on the day an image was
built, never updated afterwards, and different on every controller. Nobody
could say which Caddy a device serves the panel's TLS with, and nothing could
change it short of a reflash.

The templates now pin ``caddy:2.11.4-alpine`` by the digest of its multi-arch
index, so every controller that takes a release runs the same bytes, and a
release that bumps the pin is the only thing that moves it. The live compose
file is not rewritten here: switching the image means pulling it and
recreating the container, which needs the network and drops the HTTPS panel
for a few seconds — the operator's call, from the panel, when it suits them.
That goes through two new operations in boneio-containers:

  caddy-image-state   read-only: the pinned image and the one in use
  caddy-image-apply   no argument: take the pinned image into the one image
                      line, pull it, recreate only Caddy

There is no argument because which version Caddy runs is the release's
decision, carried in a root-owned template, not the caller's.

Trusted copies go first, as in 1.6.15 and 1.6.16. ``validate="python"`` because
a helper that does not compile would take Node-RED and Caddy management down.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.21.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.21"
DESCRIPTION = "Pin the Caddy image and let the panel apply it"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    actions: list[MigrationAction] = [
        InstallFile(
            src=f"docker/nodered/{template}",
            dst=f"{_TRUSTED_DIR}/{template}",
            mode=0o644,
            owner="root",
            group="root",
        )
        for template in ("docker-compose.yaml", "docker-compose-cloud.yaml")
    ]
    for dst in (f"{_TRUSTED_DIR}/boneio-containers", "/usr/sbin/boneio-containers"):
        actions.append(
            InstallFile(
                src="helpers/boneio-containers",
                dst=dst,
                mode=0o755,
                owner="root",
                group="root",
                validate="python",
            )
        )
    return actions
