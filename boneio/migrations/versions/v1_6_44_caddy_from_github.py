"""Caddy from its GitHub release, not from its apt repository on Cloudsmith.

Caddy's Debian repository on Cloudsmith answers 402 Payment Required whenever
the project runs out of transfer quota (caddyserver/dist#142). Every
``apt-get update`` then fails on it, and the switch to the packaged Caddy
cannot install the package at all.

``boneio-containers`` now installs the armhf ``.deb`` from Caddy's GitHub
release itself, pinned by version and SHA-512 in the helper, which is signed
with these migrations. The repository 1.6.42 staged goes: its source list, its
key, the 2.11 pin and the automatic-updates origin. A Caddy already installed
from it stays; it is the same file the release publishes.

Caddy no longer takes patch releases by itself: a new Caddy comes with a
boneIO release that moves the pin.

The helper goes first, to the pristine copy as well, so
``boneio-helpers-heal.service`` does not put the apt-based one back.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.44.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction, RemoveFile

VERSION = "1.6.44"
DESCRIPTION = "Caddy from its GitHub release, not the Cloudsmith apt repository"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.44.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        *(
            InstallFile(
                src="helpers/boneio-containers", dst=dst, mode=0o755,
                owner="root", group="root", validate="python",
            )
            for dst in ("/usr/lib/boneio/trusted/boneio-containers", "/usr/sbin/boneio-containers")
        ),
        RemoveFile(path="/etc/apt/apt.conf.d/53boneio-caddy"),
        RemoveFile(path="/etc/apt/sources.list.d/caddy-stable.list"),
        RemoveFile(path="/etc/apt/preferences.d/caddy"),
        RemoveFile(path="/usr/share/keyrings/caddy-stable-archive-keyring.gpg"),
    ]
