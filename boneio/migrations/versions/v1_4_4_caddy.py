"""BoneIO 1.4.4 — Replace nginx with Caddy for reverse proxy.

Replaces the nginx-based reverse proxy with Caddy, providing:
- Self-signed HTTPS on port 8443 (out of the box)
- HTTP on port 8091 (same as before)
- Seamless upgrade path to cloud mode (wildcard SSL)
- Unified docker-compose for all deployments

Also installs Caddy init script and 502 error page.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    RemoveFile,
)

VERSION = "1.4.4"
DESCRIPTION = "Replace nginx with Caddy reverse proxy (HTTPS support)"
REQUIRES_ROOT = True

_BONEIO_USER = "boneio"
_BONEIO_HOME = f"/home/{_BONEIO_USER}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.4.4.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        # 1. Install Caddy init script (non-cloud, self-signed HTTPS)
        InstallFile(
            src="docker/nodered/caddy/init-certs.sh",
            dst=f"{_BONEIO_HOME}/docker/nodered/caddy/init-certs.sh",
            mode=0o755,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        ),

        # 2. Install 502 error page
        InstallFile(
            src="docker/nodered/caddy/502.html",
            dst=f"{_BONEIO_HOME}/docker/nodered/caddy/502.html",
            mode=0o644,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        ),

        # NOTE: docker-compose.yaml IS installed here (nginx → caddy).
        # Cloud users: registration.py auto-detects on next startup (line 184)
        # that cloud config is missing and switches back. Safe.

        # 3. Replace docker-compose.yaml (nginx → caddy)
        InstallFile(
            src="docker/nodered/docker-compose.yaml",
            dst=f"{_BONEIO_HOME}/docker/nodered/docker-compose.yaml",
            mode=0o644,
            owner=_BONEIO_USER,
            group=_BONEIO_USER,
        ),

        # 4. Remove old nginx config (no longer needed)
        RemoveFile(path=f"{_BONEIO_HOME}/docker/nodered/nginx/default.conf"),
    ]
