"""Let the proxy serve a certificate the operator uploaded.

Until now a controller had two options: cloud registration, which fetches a
real certificate and needs the cloud, or Caddy's own authority, which no
browser trusts. Anyone who wanted neither — a company with its own CA, or
somebody who obtains a Let's Encrypt certificate on a machine that can actually
answer the challenge — had nowhere to put one.

This replaces the container's start script with one that serves an uploaded
certificate when it finds one, and falls back to Caddy's own when it does not.
Devices with nothing uploaded behave exactly as before.

The certificate lives in Caddy's data directory, which is already mounted and
already belongs to the account the panel runs as. That is why this migration is
one file: no new mount, so no change to the root-owned docker-compose.yaml, and
no directory that Docker could create as root before the panel can write in it.

No restart here. The new script only changes anything once a certificate has
been uploaded, and uploading one restarts the proxy itself — so a device that
never uses this never pays for it.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.13.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.13"
DESCRIPTION = "Allow an uploaded TLS certificate"
REQUIRES_ROOT = True

_BONEIO_HOME = "/home/boneio"
_BONEIO_USER = "boneio"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="docker/nodered/caddy/init-certs.sh",
            dst=f"{_BONEIO_HOME}/docker/nodered/caddy/init-certs.sh",
            mode=0o755,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        ),
    ]
