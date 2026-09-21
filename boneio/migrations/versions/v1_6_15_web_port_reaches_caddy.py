"""Let the panel's port reach Caddy instead of being hardcoded at 8090.

``init-certs.sh`` wrote the Caddyfile with ``reverse_proxy
host.docker.internal:8090``, so Caddy proxied to 8090 whatever ``web.port``
said. That used to be a nuisance — the TLS port answered 502 while the panel
still answered directly on its new port — but a 1.6 image now ships
``web.expose: proxy``, and then the application is not listening anywhere else
either. Changing the port would leave the device reachable on nothing but the
loopback, the USB gadget link and an SSH tunnel.

The port now comes from ``WEB_PORT``, which compose interpolates from the
project's ``.env``. That file is writable by the application because the
directory is its own; the compose file beside it stays root-owned, because
``docker compose up`` executes it and that is what F-04 was about. Nothing
passed through interpolation can widen anything: it substitutes into scalar
values after the YAML is parsed, so no volume and no entrypoint can arrive
this way.

``PUBLIC_HTTPS_PORT`` is passed in for the same reason. ``init-certs.sh`` had
been building the HTTP-to-HTTPS redirect from it since the redirect was added,
and no compose file ever supplied it, so only the fallback ever applied — a
device published on any port but 8443 redirected browsers somewhere nothing
was listening.

The templates go to ``/usr/lib/boneio/trusted`` as well as to the live
directory, because that is where ``boneio-containers`` copies them from: a
trusted copy left behind would restore the old file the next time cloud mode
was switched, undoing this silently.

What this deliberately does not do is overwrite the live
``docker-compose.yaml``. A migration plan cannot tell whether this device is
running the local or the cloud template, and installing the wrong one would
take a cloud device off its own domain. The application refreshes the live file
from the matching template when the port actually changes, and a fresh image
gets it from the package.

Caddy is not restarted here either. The generated Caddyfile only changes when
the container starts, and interrupting a working panel to hand it an identical
upstream is not a trade worth making unasked. The port change that needs it
brings Caddy up itself.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.15.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.15"
DESCRIPTION = "Pass the panel's port through to the reverse proxy"
REQUIRES_ROOT = True

_BONEIO_HOME = "/home/boneio"
_BONEIO_USER = "boneio"
_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    The trusted copies go first. If a run were interrupted between them and the
    init script, a device would be left with a Caddyfile asking for ``WEB_PORT``
    and templates that do not pass it — which is the state this migration
    exists to end, so it is not one to stop halfway into.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    actions: list[MigrationAction] = []

    for template in ("docker-compose.yaml", "docker-compose-cloud.yaml"):
        actions.append(
            InstallFile(
                src=f"docker/nodered/{template}",
                dst=f"{_TRUSTED_DIR}/{template}",
                mode=0o644,
                owner="root",
                group="root",
            )
        )

    actions.append(
        InstallFile(
            src="docker/nodered/caddy/init-certs.sh",
            dst=f"{_BONEIO_HOME}/docker/nodered/caddy/init-certs.sh",
            mode=0o755,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        )
    )

    return actions
