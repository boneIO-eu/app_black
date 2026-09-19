"""Stop the device's own certificate expiring twice a day.

Caddy's internal issuer defaults to a twelve-hour leaf. For a public site
renewed automatically that is a virtue; for a certificate nobody trusts until
they decide to, it undoes the decision daily. Somebody who clicks through the
warning once, or adds an exception, or installs this device's authority on
their laptop, is back to a fresh unknown certificate by the evening.

Six months instead. The intermediate is extended to a year with it, because
Caddy refuses to start when a leaf would outlive the intermediate signing it —
which is the part that makes this two settings rather than one.

This is a change to the script the container runs at start, so it only takes
effect when Caddy is next restarted. Nothing here restarts it: the certificate
in use is valid, and interrupting the panel to replace a working certificate
with a longer-lived one is not a trade worth making unasked.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.14.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.14"
DESCRIPTION = "Issue the device certificate for six months, not twelve hours"
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
