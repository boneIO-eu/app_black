"""Show "boneIO is starting" while the panel comes up, and refresh by itself.

Caddy serves this page whenever the panel does not answer yet, which after a
power cut is the first minute or so. The old page said "Service Unavailable"
and waited for somebody to press Retry.

The container mounts this one file, and a bind-mounted file keeps pointing at
the inode it was started with, so the new page shows from the next start of the
Caddy container (every reboot), not at once.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.41"
DESCRIPTION = "A starting page that refreshes by itself"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions."""
    return [
        InstallFile(
            src="docker/nodered/caddy/502.html",
            dst="/home/boneio/docker/nodered/caddy/502.html",
            mode=0o644, owner="boneio", group="boneio",
        ),
    ]
